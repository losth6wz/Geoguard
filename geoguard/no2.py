"""The Sentinel-5P analysis, extended to dated area comparisons.

Earth Engine authentication is required only when query_no2 is called.
The 0.01 degree L3 grid is not the instrument's true resolving power.
"""
from datetime import datetime, timezone, timedelta
import base64
import math
from .core import validate_dates, validate_location, monthly_summary

BAND = 'tropospheric_NO2_column_number_density'
COLLECTIONS = {'NRTI': 'COPERNICUS/S5P/NRTI/L3_NO2', 'OFFL': 'COPERNICUS/S5P/OFFL/L3_NO2'}
VIS = {'min': 0, 'max': 0.0002, 'palette': ['000000','0000ff','800080','00ffff','008000','ffff00','ff0000']}

def unpack_stacked(features,start,end):
    """Convert the efficient one-reduction-per-area export into daily rows."""
    a,b=validate_dates(start,end)
    rows=[]
    for feature in features:
        p=feature['properties']
        for offset in range((b-a).days):
            day=a+timedelta(days=offset);key='d'+day.strftime('%Y%m%d')
            rows.append({'properties':{'site_id':p['site_id'],'date':day.isoformat(),
                        'no2_mean':p.get(key+'_mean'),'no2_count':p.get(key+'_count',0)}})
    return rows

def summarize(features, sites, start, end, radius_m, collection):
    output = []
    for site in sites:
        daily = []
        for feature in features:
            p = feature['properties']
            if p['site_id'] != site['id']:
                continue
            v = p.get('no2_mean')
            v = float(v) if v is not None and math.isfinite(float(v)) else None
            daily.append({'date': p['date'], 'value': v, 'valid_pixels': p.get('no2_count', 0)})
        daily.sort(key=lambda x: x['date'])
        values = [x['value'] for x in daily if x['value'] is not None]
        output.append({**site, 'radius_m': radius_m, 'daily': daily, 'monthly': monthly_summary(daily),
                       'mean_mol_m2': sum(values)/len(values) if values else None,
                       'valid_days': len(values), 'total_days': len(daily)})
    return {'status': 'ready' if any(x['valid_days'] for x in output) else 'no_data',
            'collection': collection, 'band': BAND, 'units': 'mol/m²', 'start': start, 'end_exclusive': end,
            'sites': output, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'method': 'Within each UTC day: mean available orbit/granule values per pixel, then spatial mean over valid L3 pixels in each buffered area. Period and monthly summaries give each usable day equal weight.',
            'quality': 'Earth Engine catalog ingestion QA mask retained. No qa_value band is assumed. Negative retrievals retained except values below -0.001 mol/m²; missing values remain null.',
            'limits': 'Atmospheric column, not ground-level concentration or AQI. Location labels do not establish emission sources. Counts are L3 grid cells, not independent satellite footprints. Changing coverage, weather and retrieval uncertainty affect comparisons.'}

def query_no2(sites, start='2026-01-01', end='2026-09-01', product='NRTI', radius_m=5000, include_map=True):
    import ee
    a,b = validate_dates(start,end)
    if product not in COLLECTIONS or not 2000 <= radius_m <= 20000 or not 1 <= len(sites) <= 5:
        raise ValueError('Use NRTI/OFFL, 2–20 km radius and 1–5 areas.')
    if len({s['id'] for s in sites}) != len(sites):
        raise ValueError('Area IDs must be unique.')
    for s in sites:
        validate_location(s['latitude'],s['longitude'])
    areas = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([s['longitude'],s['latitude']]).buffer(radius_m),
                     {'site_id': s['id']}) for s in sites])
    region = areas.geometry().bounds()
    images = (ee.ImageCollection(COLLECTIONS[product]).filterBounds(region).filterDate(start,end).select(BAND)
              .map(lambda im: im.updateMask(im.gte(-0.001))))
    if images.size().getInfo() == 0:
        raise ValueError('No source images found for this date range and region. Nothing has been classified as clean.')
    # A fully masked fallback preserves the band name on days with no observations.
    empty = ee.Image.constant(0).rename(BAND).updateMask(ee.Image.constant(0))
    def daily_image(offset):
        day = ee.Date(start).advance(offset,'day')
        source = images.filterDate(day,day.advance(1,'day'))
        im = ee.Image(ee.Algorithms.If(source.size().gt(0),source.mean(),empty)).rename('no2')
        return im.set({'system:time_start': day.millis(), 'date': day.format('YYYY-MM-dd')})
    days = ee.List.sequence(0,(b-a).days-1)
    daily = ee.ImageCollection.fromImages(days.map(daily_image))
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(),sharedInputs=True)
    # Reduce a stack of day-bands once per area. Mapping reduceRegions over
    # hundreds of days exceeds Earth Engine's concurrent-aggregation quota.
    names=['d'+(a+timedelta(days=i)).strftime('%Y%m%d') for i in range((b-a).days)]
    stack=daily.toBands().rename(names)
    stats=stack.reduceRegions(collection=areas,reducer=reducer,scale=1113.2,crs='EPSG:4326',tileScale=4)
    features=unpack_stacked(stats.getInfo()['features'],start,end)
    result = summarize(features,sites,start,end,radius_m,COLLECTIONS[product])
    if include_map and result['status']=='ready':
        # The visualization is an image, never a second source of numeric values.
        import requests
        try:
            bounds=region.coordinates().getInfo()[0]
            west,east=min(p[0] for p in bounds),max(p[0] for p in bounds)
            south,north=min(p[1] for p in bounds),max(p[1] for p in bounds)
            url=daily.mean().clip(region).getThumbURL({**VIS,'region':region,'dimensions':900,'crs':'EPSG:4326','format':'png'})
            response=requests.get(url,timeout=120);response.raise_for_status()
            if not response.content.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Map service did not return a PNG.')
            result['map']={'png_data':'data:image/png;base64,'+base64.b64encode(response.content).decode(),
                           'bounds':[west,south,east,north], 'min':VIS['min'],'max':VIS['max'],
                           'meaning':'Per-pixel mean of usable daily NO2 columns; transparent pixels have no data.'}
        except Exception as exc:
            result['map_error']='Numeric results succeeded; map unavailable: '+str(exc)
    return result
