"""Anonymous current Sentinel-2 L1C discovery and small GCS pixel crops.

No methane claims are made here. Product-level TOA calibration is preserved;
cloud classification and MARS inference are deliberately separate.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
import requests
import rasterio
from rasterio.transform import Affine, array_bounds
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds, Window
from pyproj import Transformer
from shapely.geometry import box, shape, mapping
from shapely.ops import transform as geometry_transform

BANDS = ['B01','B02','B03','B04','B05','B06','B07','B08','B8A','B09','B10','B11','B12']
DETECTOR_BANDS = ['B02','B03','B04','B08','B11','B12']
CATALOG = 'https://stac.dataspace.copernicus.eu/v1/search'
BUCKET = 'https://storage.googleapis.com/gcp-public-data-sentinel-2/'
LIST_API = 'https://storage.googleapis.com/storage/v1/b/gcp-public-data-sentinel-2/o'

def _utc(value=None):
    if value is None: return dt.datetime.now(dt.timezone.utc)
    if isinstance(value,str): value=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None: value=value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)

def _check_point(latitude,longitude):
    if not math.isfinite(latitude) or not -90<=latitude<=90: raise ValueError('Invalid latitude')
    if not math.isfinite(longitude) or not -180<=longitude<=180: raise ValueError('Invalid longitude')

def discover(latitude, longitude, lookback_days=90, as_of=None):
    """Query actual requested point. Results are catalog records, not clear pixels."""
    _check_point(latitude,longitude)
    if not 1<=lookback_days<=366: raise ValueError('lookback_days must be 1–366')
    end=_utc(as_of); start=end-dt.timedelta(days=lookback_days)
    params={'collections':'sentinel-2-l1c','bbox':f'{longitude-.00001},{latitude-.00001},{longitude+.00001},{latitude+.00001}',
            'datetime':f'{start.isoformat()}/{end.isoformat()}','limit':100,'sortby':'-properties.datetime'}
    response=requests.get(CATALOG,params=params,timeout=60);response.raise_for_status()
    data=response.json()
    if any(x.get('rel')=='next' for x in data.get('links',[])):
        raise RuntimeError('Catalog query requires pagination; reduce the lookback window')
    checked=_utc().isoformat(); result=[]
    for f in data.get('features',[]):
        p=f['properties']
        # Input-level gate: never swap in L2A/surface reflectance.
        if '_MSIL1C_' not in f['id']: continue
        result.append({'id':f['id'],'acquired_at':p['datetime'],'sensor':f['id'].split('_')[0],
          'platform':p.get('platform'),'available_at':p.get('published'),
          'catalog_created_at':p.get('created'),'checked_at':checked,
          'scene_cloud_cover':p.get('eo:cloud_cover'),'geometry':f['geometry'],
          'catalog_url':response.url,'stac':f})
    return sorted(result,key=lambda x:x['acquired_at'],reverse=True)

def _strip_ns(root):
    for element in root.iter(): element.tag=element.tag.split('}')[-1]
    return root

def _read_xml(url,path):
    r=requests.get(url,timeout=60);r.raise_for_status();path.write_bytes(r.content)
    return _strip_ns(ET.fromstring(r.content))

def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def fetch_crop(scene, latitude, longitude, cache_dir, width_m=2000):
    """Return metadata and saved raw/harmonized 13-band, 10 m nearest crops.

    The destination is snapped to a 20 m grid; SWIR remains native information.
    Apply the official cloud model BEFORE the upstream 20-to-10 m interpolation.
    """
    _check_point(latitude,longitude)
    if width_m<400 or width_m>6000 or width_m%20: raise ValueError('width_m must be 400–6000, divisible by20')
    scene_id=scene.get('id')
    if not scene_id or not re.fullmatch(r'S2[ABC]_MSIL1C_[A-Z0-9_]+',scene_id):
        raise ValueError('Only an explicit Sentinel-2 L1C product is supported')
    tile=re.search(r'_T(\d{2})([A-Z])([A-Z]{2})_',scene_id)
    if not tile: raise ValueError('Product has no MGRS tile')
    prefix=f'tiles/{tile[1]}/{tile[2]}/{tile[3]}/{scene_id}.SAFE/'
    response=requests.get(LIST_API,params={'prefix':prefix,'maxResults':1000},timeout=60)
    response.raise_for_status(); listing=response.json()
    if 'nextPageToken' in listing: raise RuntimeError('Unexpected large product listing')
    objects=listing.get('items',[])
    if not objects: raise FileNotFoundError('This catalog product is not yet present in the public GCS mirror')
    assets={}
    for band in BANDS:
        matches=[o for o in objects if o['name'].endswith('_'+band+'.jp2') and '/IMG_DATA/' in o['name']]
        if len(matches)!=1: raise RuntimeError(f'Expected one {band} asset; got {len(matches)}')
        assets[band]=matches[0]
    folder=Path(cache_dir)/f'{scene_id}_{latitude:.6f}_{longitude:.6f}_{width_m}m'
    folder.mkdir(parents=True,exist_ok=True)
    manifest_path=folder/'metadata.json'
    if manifest_path.exists():
        saved=json.loads(manifest_path.read_text(encoding='utf-8'))
        if all(Path(saved[k]).exists() and _sha(saved[k])==saved['hashes'][k] for k in ['toa13_path','raw13_path','valid13_path']): return saved
    msi_name=next(o['name'] for o in objects if o['name'].endswith('/MTD_MSIL1C.xml'))
    tile_name=next(o['name'] for o in objects if o['name'].endswith('/MTD_TL.xml'))
    msi_path=folder/'MTD_MSIL1C.xml'; tile_path=folder/'MTD_TL.xml'
    msi=_read_xml(BUCKET+msi_name,msi_path); tl=_read_xml(BUCKET+tile_name,tile_path)
    quantification=float(msi.findtext('.//QUANTIFICATION_VALUE'))
    if quantification!=10000: raise ValueError('Unsupported Sentinel-2 quantification value')
    offsets={BANDS[int(e.attrib['band_id'])]:float(e.text) for e in msi.findall('.//RADIO_ADD_OFFSET')}
    baseline=float(msi.findtext('.//PROCESSING_BASELINE'))
    if not offsets:
        if baseline>=4: raise ValueError('Modern baseline without explicit band offsets')
        offsets={b:0.0 for b in BANDS}
    if set(offsets)!=set(BANDS): raise ValueError('Incomplete radiometric offsets')
    invalid_values={int(e.findtext('SPECIAL_VALUE_INDEX')) for e in msi.findall('.//Special_Values')}
    if not invalid_values: raise ValueError('Missing declared special DN values')
    sun=tl.find('.//Mean_Sun_Angle')
    sza=float(sun.findtext('ZENITH_ANGLE'))
    vzas=[float(e.findtext('ZENITH_ANGLE')) for e in tl.findall('.//Mean_Viewing_Incidence_Angle') if int(e.attrib['bandId'])==12]
    if len(vzas)!=1: raise ValueError('Missing unique B12 incidence angle')
    acquired=tl.findtext('.//SENSING_TIME')
    env={'GDAL_DISABLE_READDIR_ON_OPEN':'EMPTY_DIR','CPL_VSIL_CURL_ALLOWED_EXTENSIONS':'.jp2',
         'GDAL_HTTP_MAX_RETRY':2,'GDAL_HTTP_TIMEOUT':90}
    rows=int(width_m/10)
    with rasterio.Env(**env):
      with rasterio.open(BUCKET+assets['B02']['name']) as src:
        crs=src.crs
        x,y=Transformer.from_crs(4326,crs,always_xy=True).transform(longitude,latitude)
        # Align with the native band grid, not arbitrary WGS84 degrees.
        left=src.transform.c+math.floor((x-width_m/2-src.transform.c)/20)*20
        top=src.transform.f+math.ceil((y+width_m/2-src.transform.f)/20)*20
        transform=Affine(10,0,left,0,-10,top)
      bounds=array_bounds(rows,rows,transform)
      requested_polygon=geometry_transform(Transformer.from_crs(crs,4326,always_xy=True).transform,box(*bounds))
      geometry=scene.get('geometry') or scene.get('stac',{}).get('geometry')
      if not geometry or not shape(geometry).covers(requested_polygon):
        raise ValueError('Scene footprint does not cover the entire requested crop')
      raw=np.zeros((len(BANDS),rows,rows),dtype=np.uint16)
      valid=np.zeros_like(raw,dtype=np.uint8)
      band_info=[]
      for i,band in enumerate(BANDS):
        with rasterio.open(BUCKET+assets[band]['name']) as src:
          if src.crs!=crs: raise ValueError('Band CRS mismatch')
          win=from_bounds(*bounds,transform=src.transform)
          # Padding ensures a full nearest sample even at non-60 m-aligned edges.
          win=Window(math.floor(win.col_off)-1,math.floor(win.row_off)-1,math.ceil(win.width)+3,math.ceil(win.height)+3)
          dn=src.read(1,window=win,boundless=True,fill_value=0)
          native_valid=(~np.isin(dn,list(invalid_values))).astype(np.uint8)
          reproject(dn,raw[i],src_transform=src.window_transform(win),src_crs=crs,dst_transform=transform,dst_crs=crs,resampling=Resampling.nearest)
          reproject(native_valid,valid[i],src_transform=src.window_transform(win),src_crs=crs,dst_transform=transform,dst_crs=crs,resampling=Resampling.nearest)
          native_path=folder/f'{band}_native.npz'
          np.savez_compressed(native_path,dn=dn,valid=native_valid,transform=np.array(tuple(src.window_transform(win))))
          band_info.append({'band':band,'native_resolution_m':list(src.res),'offset_dn':offsets[band],
            'scale':1/quantification,'public_source_url':BUCKET+assets[band]['name'],
            'provider_md5_base64':assets[band].get('md5Hash'),'provider_generation':assets[band].get('generation'),
            'provider_object_updated_at':assets[band].get('updated'),'native_crop_path':str(native_path),
            'native_crop_sha256':_sha(native_path),'invalid_fraction':float(1-valid[i].mean())})
    harmonized=np.empty_like(raw)
    for i,band in enumerate(BANDS):
        scaled=raw[i].astype(np.int32)+int(offsets[band])
        band_info[i]['clipped_nonpositive_count']=int(((scaled<=0)&(valid[i]>0)).sum())
        harmonized[i]=np.clip(scaled,0,65535).astype(np.uint16)
        harmonized[i][valid[i]==0]=0
    paths={}
    for key,arr,name in [('raw13_path',raw,'raw_l1c_dn_13bands.tif'),('toa13_path',harmonized,'harmonized_toa_x10000_13bands.tif'),('valid13_path',valid,'raw_validity_13bands.tif')]:
        path=folder/name
        with rasterio.open(path,'w',driver='GTiff',height=rows,width=rows,count=len(BANDS),dtype=arr.dtype,crs=crs,transform=transform,compress='deflate',nodata=0) as dst:
            dst.write(arr)
            for i,band in enumerate(BANDS,1): dst.set_band_description(i,band)
        paths[key]=str(path)
    metadata={'adapter_version':'gcs-s2-l1c-v1','scene_id':scene_id,'sensor':scene_id.split('_')[0],
      'acquired_at':acquired,'product_acquired_at':scene.get('acquired_at'),'available_at':scene.get('available_at'),
      'catalog_created_at':scene.get('catalog_created_at'),'fetched_at':_utc().isoformat(),
      'latitude':latitude,'longitude':longitude,'width_m':width_m,'shape':list(raw.shape),
      'band_names':BANDS,'detector_band_names':DETECTOR_BANDS,'crs':str(crs),'transform':list(transform),
      'crop_geometry':mapping(requested_polygon),'scene_footprint_covers_crop':True,'scene_geometry':geometry,
      'solar_zenith':sza,'view_zenith':vzas[0],'processing_baseline':baseline,'quantification_value':quantification,
      'special_invalid_dn_values':sorted(invalid_values),'resampling':'nearest native optical bands to aligned10m; cloud model must precede official20m interpolation',
      'scaling':'(raw DN + metadata RADIO_ADD_OFFSET) clipped0–65535 = harmonized TOA reflectance ×10000',
      'product_level':'L1C TOA','scene_cloud_cover':scene.get('scene_cloud_cover'),'bands':band_info,
      'model_parity_status':'GEE pixel parity not independently validated; public SAFE adapter is experimental',
      'metadata_path':str(manifest_path),'source_metadata_paths':[str(msi_path),str(tile_path)],**paths}
    metadata['hashes']={k:_sha(v) for k,v in paths.items()}
    metadata['source_metadata_hashes']={p.name:_sha(p) for p in [msi_path,tile_path]}
    manifest_path.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return metadata
