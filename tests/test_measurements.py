"""Scientific contract checks, independent of account access."""
import copy, json, unittest
from pathlib import Path
from geoguard.core import SITES, bundle
from geoguard.measurements import METRICS, specification, summarize_export
ROOT=Path(__file__).resolve().parents[1]
class MeasurementTests(unittest.TestCase):
    def test_actual_export_parity_and_coverage(self):
        raw=json.loads((ROOT/'sources/measurements_earthengine_export.geojson').read_text())
        demo=json.loads((ROOT/'docs/data/demo.json').read_text(encoding='utf-8'))
        for metric in ['CO','SO2','CH4']:
            rows=[f for f in raw['features'] if f['properties']['metric']==metric]
            result=summarize_export(rows,metric,SITES,'2026-08-01','2026-10-01',product='OFFL' if metric=='CH4' else 'NRTI')
            self.assertEqual(result['sites'],demo['measurements'][metric]['sites'])
            self.assertEqual(result['units'],METRICS[metric]['units'])
        self.assertEqual([s['valid_days'] for s in demo['measurements']['CH4']['sites']],[33,37])
    def test_missing_negative_and_zero_count(self):
        rows=[{'properties':{'site_id':'dubai','d20260801_mean':-.0002,'d20260801_count':4,
            'd20260802_mean':10,'d20260802_count':0}}]
        result=summarize_export(rows,'SO2',SITES[:1],'2026-08-01','2026-08-04')
        site=result['sites'][0]
        self.assertEqual(site['mean_value'],-.0002)
        self.assertEqual([d['value'] for d in site['daily']],[-.0002,None,None])
        self.assertEqual(site['valid_days'],1)
    def test_product_and_provenance_rejected(self):
        with self.assertRaises(ValueError): specification('CH4','NRTI')
        with self.assertRaises(ValueError): specification('PM25','NRTI')
        row={'properties':{'site_id':'dubai','metric':'CO','latitude':23}}
        with self.assertRaises(ValueError): summarize_export([row],'CO',SITES[:1],'2026-08-01','2026-08-03')
        row['properties']['latitude']=25.2048;row['properties']['metric']='SO2'
        with self.assertRaises(ValueError): summarize_export([row],'CO',SITES[:1],'2026-08-01','2026-08-03')
    def test_empty_is_unknown_and_bundle_backwards_compatible(self):
        value=summarize_export([],'CH4',SITES,'2026-08-01','2026-08-03',product='OFFL')
        self.assertEqual(value['status'],'no_data')
        self.assertTrue(all(s['mean_value'] is None for s in value['sites']))
        self.assertEqual(bundle(None,None,{'CH4':value})['measurements']['CH4'],value)
        self.assertEqual(bundle()['measurements'],{})
