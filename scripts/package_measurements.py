"""Package verified Earth Engine inputs; no generated placeholder observations."""
from pathlib import Path
import json, base64
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geoguard.core import SITES
from geoguard.measurements import summarize_export, METRICS, PALETTE

def package(bounds):
    raw=json.loads((ROOT/'sources/measurements_earthengine_export.geojson').read_text())
    demo=json.loads((ROOT/'docs/data/demo.json').read_text(encoding='utf-8'))
    results={}
    for metric in ['CO','SO2','CH4']:
        features=[f for f in raw['features'] if f['properties']['metric']==metric]
        result=summarize_export(features,metric,SITES,'2026-08-01','2026-10-01',product='OFFL' if metric=='CH4' else 'NRTI')
        spec=METRICS[metric]
        png=(ROOT/f'docs/assets/{metric.lower()}-example.png').read_bytes()
        assert png.startswith(b'\x89PNG\r\n\x1a\n')
        result['map']={'png_data':'data:image/png;base64,'+base64.b64encode(png).decode(),'bounds':bounds,
            'min':spec['min'],'max':spec['max'],'units':spec['units'],'palette':PALETTE,
            'meaning':spec['quantity']+'; mean usable daily pixels. Transparent means missing.'}
        result['source_export']='sources/measurements_earthengine_export.geojson'
        result['retrieved_at']='2026-10-07'
        results[metric]=result
    demo['measurements']=results
    demo['interpretation']='Atmospheric quantities and methane candidates remain separate. No AQI, surface exposure, emission rate or health verdict.'
    (ROOT/'docs/data/demo.json').write_text(json.dumps(demo,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    config=json.loads((ROOT/'examples/input.json').read_text())
    config.update(measurements_source='sources/measurements_earthengine_export.geojson',measurements_start='2026-08-01',measurements_end_exclusive='2026-10-01',mode='recompute_saved_satellite_measurements_and_replay_dated_methane')
    (ROOT/'examples/input.json').write_text(json.dumps(config,indent=2)+'\n')
    expected=json.loads((ROOT/'examples/expected_summary.json').read_text())
    expected['measurements']={k:[{field:s[field] for field in ['id','mean_value','valid_days','total_days']} for s in v['sites']] for k,v in results.items()}
    (ROOT/'examples/expected_summary.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    import sys
    package(json.loads(sys.argv[1]))
