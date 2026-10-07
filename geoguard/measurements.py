"""Supported satellite quantities. No gas is converted to AQI or surface exposure."""
from datetime import timedelta, datetime, timezone
import base64
import math
from .core import validate_dates, validate_location, monthly_summary

METRICS = {
    'NO2': {'label': 'NO₂', 'name': 'Nitrogen dioxide', 'band': 'tropospheric_NO2_column_number_density',
            'products': ['NRTI', 'OFFL'], 'units': 'mol/m²', 'display_units': 'µmol/m²', 'display_factor': 1e6,
            'quantity': 'Tropospheric NO₂ column', 'min': 0, 'max': .0002},
    'CO': {'label': 'CO', 'name': 'Carbon monoxide', 'band': 'CO_column_number_density',
           'products': ['NRTI', 'OFFL'], 'units': 'mol/m²', 'display_units': 'mmol/m²', 'display_factor': 1e3,
           'quantity': 'Total atmospheric CO column', 'min': 0, 'max': .05},
    'SO2': {'label': 'SO₂', 'name': 'Sulfur dioxide', 'band': 'SO2_column_number_density',
            'products': ['NRTI', 'OFFL'], 'units': 'mol/m²', 'display_units': 'µmol/m²', 'display_factor': 1e6,
            'quantity': 'Atmospheric SO₂ vertical column (ground-level profile assumption)', 'min': -.0001, 'max': .0005},
    'CH4': {'label': 'CH₄ regional', 'name': 'Regional methane', 'band': 'CH4_column_volume_mixing_ratio_dry_air_bias_corrected',
            'products': ['OFFL'], 'units': 'ppb', 'display_units': 'ppb', 'display_factor': 1,
            'quantity': 'Column-averaged dry-air CH₄ mixing ratio, albedo-bias-corrected', 'min': 1800, 'max': 2000},
}
PALETTE = ['222266', '407bbb', '77b9c7', 'e1eab9', 'f4be64', 'ce5942']

def specification(metric, product):
    if metric not in METRICS or product not in METRICS[metric]['products']:
        raise ValueError('Choose NO2/CO/SO2 with NRTI or OFFL, or CH4 with OFFL only.')
    return METRICS[metric]

def summarize_export(raw, metric, sites, start, end, radius_m=5000, product='NRTI'):
    """Recalculate dates and summaries from actual stacked Earth Engine reductions."""
    spec = specification(metric, product)
    a, b = validate_dates(start, end)
    if not 2000 <= radius_m <= 20000 or not 1 <= len(sites) <= 5 or len({s['id'] for s in sites}) != len(sites):
        raise ValueError('Use 1–5 distinct sites and a 2–20 km radius.')
    collection = f'COPERNICUS/S5P/{product}/L3_{metric}'
    features = raw['features'] if isinstance(raw, dict) else raw
    by_id = {}
    for feature in features:
        prop = feature['properties']
        if prop['site_id'] in by_id:
            raise ValueError('Duplicate site reduction.')
        if prop.get('metric', metric) != metric or prop.get('collection', collection) != collection:
            raise ValueError('Export identity does not match the selected metric/product.')
        by_id[prop['site_id']] = prop
    output = []
    for site in sites:
        validate_location(site['latitude'], site['longitude'])
        prop = by_id.get(site['id'], {})
        if any(key in prop and prop[key] != expected for key, expected in
               [('start', start), ('end_exclusive', end), ('radius_m', radius_m),
                ('latitude', site['latitude']), ('longitude', site['longitude'])]):
            raise ValueError('Export dates, area or coordinates do not match the requested study.')
        daily = []
        for offset in range((b-a).days):
            day = a + timedelta(days=offset)
            key = 'd' + day.strftime('%Y%m%d')
            value, count = prop.get(key+'_mean'), prop.get(key+'_count', 0)
            if not isinstance(count, (int, float)) or not math.isfinite(count) or count < 0:
                raise ValueError('Invalid valid-pixel count.')
            value = float(value) if value is not None and math.isfinite(float(value)) and count > 0 else None
            # Defensive parity with the live query, not a positivity filter.
            if value is not None and ((metric != 'CH4' and value < -.001) or (metric == 'CH4' and value <= 0)):
                value = None
            daily.append({'date': day.isoformat(), 'value': value, 'valid_pixels': count})
        values = [r['value'] for r in daily if r['value'] is not None]
        output.append({**site, 'radius_m': radius_m, 'daily': daily, 'monthly': monthly_summary(daily),
                       'mean_value': sum(values)/len(values) if values else None,
                       'valid_days': len(values), 'total_days': len(daily)})
    result = {'metric': metric, 'status': 'ready' if any(s['valid_days'] for s in output) else 'no_data',
              'collection': collection, 'band': spec['band'], 'quantity': spec['quantity'],
              'units': spec['units'], 'display_units': spec['display_units'], 'display_factor': spec['display_factor'],
              'start': start, 'end_exclusive': end, 'sites': output,
              'retrieved_at': datetime.now(timezone.utc).isoformat(),
              'method': 'Mean available granules per UTC day; spatial reduction over valid L3 grid cells; equal weight per usable day.',
              'quality': 'Inherited Earth Engine ingestion mask. Missing cells/days remain null; valid negative columns retained above -0.001 mol/m².',
              'limits': 'Atmospheric quantity, not surface exposure, AQI, an emission rate or a source attribution. Display colors are not safety thresholds. L3 grid cells are not independent instrument footprints.'}
    if metric == 'CH4':
        result['quality'] = 'Inherited catalogue mask; positive albedo-bias-corrected XCH4 retained. Catalogue warns of residual stripes and inland-water artifacts. No validated total uncertainty is calculated.'
        result['limits'] += ' Regional XCH4 is not a local leak measurement or the Sentinel-2 detector score. OFFL retrievals may be sparse.'
    return result

def query_measurement(metric, sites, start, end, product='NRTI', radius_m=5000, include_map=True):
    import ee
    spec = specification(metric, product)
    a, b = validate_dates(start, end)
    # Validate before any remote work, using the same evidence contract.
    summarize_export([], metric, sites, start, end, radius_m, product)
    collection = f'COPERNICUS/S5P/{product}/L3_{metric}'
    areas = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([s['longitude'], s['latitude']]).buffer(radius_m),
        {'site_id': s['id'], 'metric': metric, 'collection': collection, 'start': start, 'end_exclusive': end,
         'radius_m': radius_m, 'latitude': s['latitude'], 'longitude': s['longitude']}) for s in sites])
    region = areas.geometry().bounds()
    images = ee.ImageCollection(collection).filterBounds(region).filterDate(start, end).select(spec['band'])
    images = images.map(lambda image: image.updateMask(image.gt(0) if metric == 'CH4' else image.gte(-.001)))
    empty = ee.Image.constant(0).rename(spec['band']).updateMask(ee.Image.constant(0))
    def make_day(offset):
        day = ee.Date(start).advance(offset, 'day')
        source = images.filterDate(day, day.advance(1, 'day'))
        return ee.Image(ee.Algorithms.If(source.size().gt(0), source.mean(), empty)).rename('value').set('system:time_start', day.millis())
    count = (b-a).days
    daily = ee.ImageCollection.fromImages(ee.List.sequence(0, count-1).map(make_day))
    names = ['d'+(a+timedelta(days=i)).strftime('%Y%m%d') for i in range(count)]
    stats = daily.toBands().rename(names).reduceRegions(collection=areas,
        reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True), scale=1113.2, crs='EPSG:4326', tileScale=4)
    raw = stats.getInfo()
    result = summarize_export(raw, metric, sites, start, end, radius_m, product)
    if include_map and result['status'] == 'ready':
        import requests
        try:
            bounds = region.coordinates().getInfo()[0]
            west,east = min(p[0] for p in bounds),max(p[0] for p in bounds)
            south,north = min(p[1] for p in bounds),max(p[1] for p in bounds)
            url = daily.mean().clip(region).getThumbURL({'min': spec['min'], 'max': spec['max'],
                'palette': PALETTE, 'region': region, 'dimensions': 900, 'crs': 'EPSG:4326', 'format': 'png'})
            response = requests.get(url, timeout=120); response.raise_for_status()
            if not response.content.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Map service did not return PNG.')
            result['map'] = {'png_data': 'data:image/png;base64,'+base64.b64encode(response.content).decode(),
                'bounds': [west,south,east,north], 'min': spec['min'], 'max': spec['max'],
                'units': spec['units'], 'meaning': spec['quantity']+'; mean usable daily pixels. Transparent means missing.', 'palette': PALETTE}
        except Exception as exc:
            result['map_error'] = 'Numeric results succeeded; map unavailable: '+str(exc)
    return result
