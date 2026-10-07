"""Small, testable data contract shared by the notebook and website."""
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

SITES = [
    {"id": "dubai", "name": "Dubai comparison area", "latitude": 25.2048, "longitude": 55.2708},
    {"id": "jebel-ali", "name": "Jebel Ali comparison area", "latitude": 25.0083, "longitude": 55.0875},
]
SAVED_SITE = {"id": "uae-example", "name": "Previously tested UAE area", "latitude": 23.86479, "longitude": 53.61893}

def validate_location(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not all(math.isfinite(v) for v in (lat, lon)) or not (22 <= lat <= 27 and 51 <= lon <= 57):
        raise ValueError("Choose a point in the UAE study region (latitude 22–27, longitude 51–57). The methane engine also checks the land boundary.")
    return lat, lon

def validate_dates(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if not a < b:
        raise ValueError("End date must be after start date; the end date is excluded.")
    if (b-a).days > 366:
        raise ValueError("Choose at most 366 days per query to keep the notebook responsive.")
    return a, b

def monthly_summary(daily):
    """Equal weight per valid day; preserve missing and negative observations."""
    groups = {}
    for row in daily:
        bucket = groups.setdefault(row['date'][:7], [])
        v = row.get('value')
        if v is not None and math.isfinite(float(v)):
            bucket.append(float(v))
    return [{'month': month, 'value': sum(v)/len(v) if v else None, 'valid_days': len(v)}
            for month, v in sorted(groups.items())]

def public_methane(result, figure_data=None):
    """Export scientific evidence without private local paths or credentials."""
    keys = ['status', 'message', 'checked_at', 'current_acquired_at', 'background_acquired_at',
            'current_product_id', 'background_product_id', 'provider_available_at', 'latitude',
            'longitude', 'requested_bounds', 'pipeline_version', 'model_id', 'weights_sha256',
            'candidate_pixels', 'common_valid_fraction', 'history_count', 'forecast', 'limits']
    data = {k: result[k] for k in keys if k in result}
    wind = result.get('wind') or {}
    data['wind_source'] = wind.get('source')
    data['wind_fallback_used'] = wind.get('fallback_used')
    if figure_data:
        data['figure_data'] = figure_data
    return data

def bundle(no2=None, methane=None, measurements=None):
    return {'schema': 'geoguard-demo-v1', 'exported_at': datetime.now(timezone.utc).isoformat(),
            'no2': no2, 'methane': methane, 'measurements': measurements or {},
            'interpretation': 'Atmospheric columns, regional methane mixing ratio and detailed methane candidate scores are separate quantities. No overall safe/polluted verdict is calculated.'}

def export_bundle(path, no2=None, methane=None, measurements=None):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bundle(no2, methane, measurements), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return p
