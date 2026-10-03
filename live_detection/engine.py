"""Latest-image methane screening with traceable inputs and persistent history.

The pretrained checkpoint is unchanged. This public SAFE acquisition adapter is
experimental; outputs are candidate detections, never calibrated gas amounts.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile
import warnings

import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.warp import transform_geom
from pyproj import Geod
from shapely.geometry import Point, shape, box
from shapely.ops import unary_union
from scipy import ndimage
import torch

from .acquisition import discover, fetch_crop
from .auxiliary import prepare_crop, wind_for_scene
from .history import HistoryStore, aoi_hash
from guided_colab.detection_helpers import GeoGuardDetector, SHA256, _connected_mask, _rgb

VERSION = 'asap-s2-v2'
MIN_VALID = .95  # Explicit engineering gate; not an independently validated detection limit.
MODEL_HASH = SHA256['best_epoch']

def now():
    return datetime.now(timezone.utc).isoformat()

def utc(s):
    return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)

def bounds_for(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not np.isfinite([lat,lon]).all() or not (-90<lat<90 and -180<=lon<=180):
        raise ValueError('Enter valid latitude and longitude.')
    g=Geod(ellps='WGS84')
    return [g.fwd(lon,lat,270,1000)[0],g.fwd(lon,lat,180,1000)[1],
            g.fwd(lon,lat,90,1000)[0],g.fwd(lon,lat,0,1000)[1]]

def read(path):
    with rasterio.open(path) as src:
        return src.read(),src.profile.copy()

def save_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def cache_intact(result):
    """Only reuse a completed run when its evidence files are still intact."""
    required={'score','candidate_mask','valid_mask','outline','figure','manifest','history'}
    paths=result.get('paths',{})
    hashes=result.get('artifact_hashes',{})
    try:
        return (required <= paths.keys() and required <= hashes.keys()
                and all(Path(paths[k]).is_file() and sha(paths[k])==hashes[k] for k in required)
                and all(Path(paths[k]).is_file() for k in ('result','bundle')))
    except (KeyError,OSError,TypeError):
        return False

class LatestDetector:
    def __init__(self, workspace='geoguard_asap'):
        self.root=Path(workspace).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'history.sqlite'
        shared_pixels=Path(__file__).resolve().parent/'cache'
        self.pixelcache=shared_pixels if shared_pixels.exists() else self.root/'pixels'
        self.detector=GeoGuardDetector(self.root/'model',self.root/'inference')
        # Reuse the already hash-verified project checkpoint when running locally.
        existing=Path(__file__).resolve().parents[1]/'data'
        if (existing/'best_epoch').exists():
            self.detector.cache_dir=existing
        boundary_path=Path(__file__).resolve().parents[1]/'uae/data/country_boundary.geojson'
        self.boundary=json.loads(boundary_path.read_text(encoding='utf-8'))
        self.country=unary_union([shape(f['geometry']) for f in self.boundary['features']])

    def history(self, latitude, longitude):
        ident=aoi_hash(bounds_for(latitude,longitude))
        with HistoryStore(self.db) as store:
            return {'records':store.records(ident),'forecast':store.forecast_readiness(ident),'aoi_id':ident}

    def _record(self, scene, bounds, status, detail, quality='unknown', inferred=None):
        record={'requested_bounds':bounds,'product_id':scene['id'],
                'product_version':VERSION+'-'+(re.search(r'_N(\d+)_',scene['id']).group(1)),
                'sensor':scene['sensor'],'model_id':'MARS-S2L/MARSS2L_20250326',
                'model_hash':MODEL_HASH,'acquired_at':scene['acquired_at'],
                'provider_available_at':scene.get('available_at'), 'fetched_at':scene.get('fetched_at',inferred or now()),
                'inferred_at':inferred,'status':status,'quality_status':quality,'details':detail}
        with HistoryStore(self.db) as store:
            return store.record(record)

    def _prepared(self, scene, lat, lon):
        crop=fetch_crop(scene,lat,lon,self.pixelcache,width_m=2000)
        ready=prepare_crop(crop,self.pixelcache)
        image,profile=read(ready['image_path'])
        valid,_=read(ready['valid_path'])
        valid=valid[0].astype(bool)
        if image.shape!=(6,200,200) or valid.shape!=(200,200):
            raise ValueError('Unexpected model grid or band count.')
        # Boundaries constrain land/island screening. They do not certify legal borders.
        geoms=[(transform_geom('EPSG:4326',profile['crs'],f['geometry']),1) for f in self.boundary['features']]
        land=rasterize(geoms,out_shape=(200,200),transform=profile['transform']).astype(bool)
        valid &= land & np.isfinite(image).all(axis=0) & (image>0).all(axis=0)
        return crop,ready,image.astype(np.float32),valid,profile

    def run(self, latitude, longitude, progress=lambda message: None):
        lat,lon=float(latitude),float(longitude)
        bounds=bounds_for(lat,lon)
        if not self.country.covers(Point(lon,lat)):
            return {'status':'not_assessable','message':'Choose a point within the UAE land/island boundary. Offshore screening is not supported.',
                    'checked_at':now(),'requested_bounds':bounds,'paths':{}}
        ident=aoi_hash(bounds)
        out=self.root/'results'/ident
        out.mkdir(parents=True,exist_ok=True)
        progress('Checking the public catalog for new Sentinel-2 images…')
        scenes=discover(lat,lon,lookback_days=90,progress=progress)
        receipt={'checked_at':now(),'latitude':lat,'longitude':lon,
                 'scenes':[{k:v for k,v in s.items() if k!='stac'} for s in scenes]}
        save_json(out/'catalog_check.json',receipt)
        if not scenes:
            return {'status':'not_assessable','message':'No Sentinel-2 L1C catalog records found in the last 90 days.',
                    'checked_at':now(),'requested_bounds':bounds,'paths':{}}
        latest_time=scenes[0]['acquired_at']
        final_path=out/'result.json'
        if final_path.exists():
            old=json.loads(final_path.read_text(encoding='utf-8'))
            if old.get('newest_catalog_id')==scenes[0]['id'] and old.get('current_product_id')==scenes[0]['id'] and old.get('pipeline_version')==VERSION and old.get('status') in ['candidate','no_candidate'] and cache_intact(old):
                old.update(checked_at=now(),reused=True,message='No newer catalog image. Showing the last completed screening with its original image time.')
                progress(old['message'])
                return old
        failures=[]
        current=None
        # Bounded query: three latest acquisitions; cloudy/new unavailable images remain logged.
        for scene in scenes[:3]:
            try:
                progress('Reading actual image pixels and checking clouds: '+scene['acquired_at'][:10])
                c=self._prepared(scene,lat,lon)
                if c[3].mean()<MIN_VALID:
                    raise ValueError(f'Only {c[3].mean():.1%} of this 2 km tile passes the clear/valid/land checks; the configured gate is 95%.')
                current=(scene,*c)
                break
            except Exception as exc:
                reason=f'{type(exc).__name__}: {exc}'
                failures.append({'product_id':scene['id'],'reason':reason})
                self._record(scene,bounds,'not_assessable',{'reason':reason,'phase':'current_input'},'unknown')
        if current is None:
            result={'status':'not_assessable','message':'The newest images could not be assessed. See the recorded input/quality reasons.',
                    'checked_at':now(),'requested_bounds':bounds,'failures':failures,'paths':{},'newest_catalog_acquired_at':latest_time}
            save_json(out/'last_attempt.json',result)
            return result
        scene,crop,ready,image,valid,profile=current
        current_time=crop['acquired_at']
        earlier=[s for s in scenes if (utc(scene['acquired_at'])-utc(s['acquired_at'])).total_seconds()>=300 and s['id']!=scene['id']]
        candidates=[]
        from marss2l.mars_sentinel2.utils import corregister_images
        from marss2l.mars_sentinel2.mixing_ratio_methane import difference_bands
        from georeader.geotensor import GeoTensor
        for bgscene in earlier[:3]:
            try:
                progress('Checking an earlier reference image: '+bgscene['acquired_at'][:10])
                bc,br,bi,bv,bp=self._prepared(bgscene,lat,lon)
                if (utc(current_time)-utc(bc['acquired_at'])).total_seconds()<300:
                    raise ValueError('Background must be at least five minutes earlier; same-pass/tandem images are excluded.')
                if bp['crs']!=profile['crs'] or bp['transform']!=profile['transform']:
                    raise ValueError('Current and background pixel grids differ.')
                if bv.mean()<MIN_VALID:
                    raise ValueError('Reference fails the configured 95% clear/valid/land gate.')
                with warnings.catch_warnings(record=True) as alignment_warnings:
                    warnings.simplefilter('always')
                    aligned,warp,sync=corregister_images(bi,image,rgb_bands=[3,2,1],max_translations=5)
                failed_alignment=[str(w.message) for w in alignment_warnings
                                  if 'Could not calculate the warp matrix' in str(w.message)
                                  or 'Estimated translation is too large' in str(w.message)]
                if failed_alignment or not np.isfinite(warp).all():
                    raise ValueError('Reference alignment failed: '+ '; '.join(failed_alignment))
                aligned_valid=sync.warp_feature(img=bv[None].astype(np.float32),warp_matrix=warp)[0]>.999
                combined=valid & aligned_valid & np.isfinite(aligned).all(axis=0) & (aligned>0).all(axis=0)
                combined=ndimage.binary_erosion(combined,iterations=2,border_value=0)
                if combined.mean()<.90:
                    raise ValueError('Less than 90% common valid coverage after alignment and edge masking.')
                curr_gt=GeoTensor(image.copy(),profile['transform'],profile['crs'],fill_value_default=0)
                bg_gt=GeoTensor(aligned.copy(),profile['transform'],profile['crs'],fill_value_default=0)
                val_gt=GeoTensor(combined,profile['transform'],profile['crs'],fill_value_default=False)
                diff=difference_bands(curr_gt,bg_gt,[0,1,2,4],val_gt,val_gt,corregister=False)
                similarity=float(np.mean(diff.values[combined]))
                if not np.isfinite(similarity): raise ValueError('Invalid background similarity.')
                candidates.append((similarity,bgscene,bc,br,aligned,combined,np.asarray(warp).tolist()))
            except Exception as exc:
                failures.append({'product_id':bgscene['id'],'phase':'background','reason':f'{type(exc).__name__}: {exc}'})
        if not candidates:
            message='No usable earlier reference image among the three checked candidates. Detection is unavailable for this attempt.'
            self._record(scene,bounds,'not_assessable',{'reason':message,'failures':failures},'unknown')
            return {'status':'not_assessable','message':message,'checked_at':now(),'current_acquired_at':current_time,
                    'requested_bounds':bounds,'paths':{},'failures':failures}
        similarity,bgscene,bc,br,background,combined,warp=min(candidates,key=lambda x:x[0])
        progress('Getting wind conditions for the satellite acquisition time…')
        try:
            wind=wind_for_scene(lat,lon,current_time,self.pixelcache)
        except Exception as exc:
            message='Acquisition-time wind is unavailable; the model was not run. '+str(exc)
            self._record(scene,bounds,'not_assessable',{'reason':message},'unknown')
            return {'status':'not_assessable','message':message,'checked_at':now(),'current_acquired_at':current_time,
                    'requested_bounds':bounds,'paths':{},'failures':failures}
        progress('Running the earlier pretrained methane model on these new pixels…')
        model=self.detector.load_model()
        # Match the official operational tensor: divide TOA×10000 by5000 without
        # introducing the clipping in the separate prepared-dataset demonstration.
        tensor=np.concatenate([image,background]).astype(np.float32)/5000
        uv=np.array([wind['u'],wind['v']],dtype=np.float32)
        if not np.isfinite(uv).all(): raise ValueError('Invalid wind vector.')
        from marss2l.mbmp_torch import to_mbmp
        mbmp=to_mbmp(torch.from_numpy(tensor),4,5,10,11).numpy()
        x=np.concatenate([mbmp[None],tensor,np.broadcast_to((uv/8)[:,None,None],(2,200,200)),(~combined)[None].astype(np.float32)])
        if not np.isfinite(x).all(): raise ValueError('Non-finite network input; no detection result assigned.')
        with torch.inference_mode():
            score=torch.sigmoid(model({'y_context_ls0_0':torch.from_numpy(x)[None]}))[0].numpy()
        score[~combined]=0
        mask=_connected_mask(score)
        status='candidate' if mask.any() else 'no_candidate'
        inferred=now()
        paths={}
        for key,values in [('score',score.astype('float32')),('candidate_mask',mask.astype('uint8')),('valid_mask',combined.astype('uint8'))]:
            path=out/(key+'.tif')
            with rasterio.open(path,'w',**{**profile,'count':1,'dtype':str(values.dtype),'nodata':None,'compress':'deflate'}) as dst: dst.write(values,1)
            paths[key]=str(path)
        outline={'type':'FeatureCollection','features':[{'type':'Feature','geometry':transform_geom(profile['crs'],'EPSG:4326',g),'properties':{'meaning':'Unreviewed methane-like candidate'}} for g,v in shapes(mask.astype('uint8'),mask=mask,transform=profile['transform']) if v]}
        save_json(out/'outline.geojson',outline);paths['outline']=str(out/'outline.geojson')
        result={'status':status,'message':('A methane-like candidate needs analyst review.' if mask.any() else 'No methane-like candidate passed this detector’s threshold. This does not establish clean air.'),
          'checked_at':now(),'inferred_at':inferred,'current_acquired_at':current_time,
          'background_acquired_at':bc['acquired_at'],'newest_catalog_acquired_at':latest_time,'newest_catalog_id':scenes[0]['id'],
          'current_product_id':scene['id'],'background_product_id':bgscene['id'],'provider_available_at':crop.get('available_at'),
          'latitude':lat,'longitude':lon,'requested_bounds':bounds,'actual_crop_geometry':crop['crop_geometry'],
          'pipeline_version':VERSION,'model_id':'MARS-S2L/MARSS2L_20250326','weights_sha256':MODEL_HASH,
          'candidate_pixels':int(mask.sum()),'common_valid_fraction':float(combined.mean()),'background_difference':similarity,
          'checked_backgrounds':len(earlier[:3]),'usable_backgrounds':len(candidates),'alignment_warp':warp,
          'wind':wind,'failures':failures,'paths':paths,'reused':False,
          'limits':['Experimental new-area screening; public SAFE adapter not independently validated against GEE pixels.',
                    'The reference is earlier and spectrally similar, but is not independently proven plume-free.',
                    'Scores are not calibrated probabilities or methane concentration; no emission quantity is computed.',
                    'SWIR native resolution is20m;10m processing does not create additional spatial detail.',
                    'Quality thresholds and bounded three-image searches are engineering choices, not proven detection limits.']}
        self._figure(out,image,background,score,mask,combined,mbmp,result)
        paths['figure']=str(out/'screening.png')
        # Use the same catalog acquisition reference on failed and successful
        # attempts; retain the more specific granule sensing time separately.
        self._record({**scene,'fetched_at':crop['fetched_at']},bounds,status,
                     {'candidate_pixels':int(mask.sum()),'background_product_id':bgscene['id'],
                      'tile_acquired_at':current_time,'catalog_acquired_at':scene['acquired_at'],
                      'pipeline_version':VERSION,'limits':result['limits'],'wind_source':wind.get('source'),
                      'common_valid_fraction':float(combined.mean())},'usable',inferred)
        hist=self.history(lat,lon)
        result['history_count']=len(hist['records']);result['forecast']=hist['forecast']
        save_json(out/'history.json',hist)
        manifest={'current':crop,'current_preprocessing':ready,'background':bc,'background_preprocessing':br,
                  'wind':wind,'background_selection':'Minimum official normalized band difference among up to three earlier clear references',
                  'source_hashes':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
                  'weights_sha256':MODEL_HASH,'result_interpretation':result['limits']}
        save_json(out/'input_manifest.json',manifest)
        paths['result']=str(final_path);paths['manifest']=str(out/'input_manifest.json');paths['history']=str(out/'history.json')
        paths['bundle']=str(out/'GeoGuard_latest_evidence.zip')
        result['artifact_hashes']={key:sha(paths[key]) for key in
                                  ('score','candidate_mask','valid_mask','outline','figure','manifest','history')}
        save_json(final_path,result)
        with zipfile.ZipFile(paths['bundle'],'w',zipfile.ZIP_DEFLATED) as z:
            for key,path in paths.items():
                if key!='bundle': z.write(path,Path(path).name)
            z.write(out/'catalog_check.json','catalog_check.json')
        progress('Screening complete. Dates, result and history are ready.')
        return result

    def _figure(self,out,image,background,score,mask,valid,mbmp,result):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,2,figsize=(10,9))
        axes[0,0].imshow(_rgb(background));axes[0,0].set_title('Earlier reference · '+result['background_acquired_at'][:10])
        axes[0,1].imshow(_rgb(image));axes[0,1].set_title('New observation · '+result['current_acquired_at'][:10])
        if mask.any():axes[0,1].contour(mask,levels=[.5],colors=['yellow'],linewidths=1)
        im=axes[1,0].imshow(np.where(valid,mbmp-1,np.nan),cmap='RdBu_r',vmin=-.08,vmax=.08)
        axes[1,0].set_title('Normalized band ratio minus1');fig.colorbar(im,ax=axes[1,0],shrink=.7)
        im=axes[1,1].imshow(np.where(valid,score,np.nan),cmap='magma',vmin=0,vmax=1)
        axes[1,1].set_title('AI score · not gas concentration');fig.colorbar(im,ax=axes[1,1],shrink=.7)
        for ax in axes.flat:ax.set_axis_off()
        fig.suptitle('GeoGuard · '+('Unreviewed candidate' if mask.any() else 'No candidate flagged'),fontsize=16)
        fig.text(.5,.02,'2 km tile · native SWIR20m, processing grid10m · Experimental screening; no ground truth supplied',ha='center',fontsize=9)
        fig.tight_layout(rect=[0,.04,1,.96]);fig.savefig(out/'screening.png',dpi=150);plt.close(fig)
