import ast
import json
import math
from pathlib import Path
import tempfile
import unittest
from geoguard.core import validate_dates, validate_location, monthly_summary, public_methane, export_bundle, SITES
from geoguard.no2 import summarize, unpack_stacked

ROOT=Path(__file__).resolve().parents[1]

class ScientificDataTests(unittest.TestCase):
    def test_end_date_is_exclusive(self):
        a,b=validate_dates('2026-01-01','2026-09-01')
        self.assertEqual((b-a).days,243)
    def test_bad_date_ranges(self):
        for a,b in [('2026-09-01','2026-01-01'),('2026-01-01','2026-01-01'),('2024-01-01','2026-01-01')]:
            with self.assertRaises(ValueError):validate_dates(a,b)
    def test_location_validation(self):
        self.assertEqual(validate_location(25.2048,55.2708),(25.2048,55.2708))
        for lat,lon in [(float('nan'),55),(25,float('inf')),(55,25),(26,44)]:
            with self.assertRaises(ValueError):validate_location(lat,lon)
    def test_missing_is_not_zero_and_negative_is_retained(self):
        rows=[{'date':'2026-01-01','value':None},{'date':'2026-01-02','value':-1e-5},{'date':'2026-01-03','value':3e-5},{'date':'2026-02-01','value':None}]
        got=monthly_summary(rows)
        self.assertAlmostEqual(got[0]['value'],1e-5)
        self.assertEqual(got[0]['valid_days'],2)
        self.assertIsNone(got[1]['value'])
    def test_stacked_export_preserves_all_days(self):
        rows=unpack_stacked([{'properties':{'site_id':'dubai','d20260101_mean':-1e-5,'d20260101_count':12}}],'2026-01-01','2026-01-03')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['properties']['no2_mean'],-1e-5)
        self.assertIsNone(rows[1]['properties']['no2_mean'])
    def test_no_data_is_explicit(self):
        rows=unpack_stacked([{'properties':{'site_id':'dubai'}}],'2026-01-01','2026-01-03')
        got=summarize(rows,[SITES[0]],'2026-01-01','2026-01-03',5000,'test-fixture')
        self.assertEqual(got['status'],'no_data');self.assertIsNone(got['sites'][0]['mean_mol_m2'])
        self.assertEqual(got['sites'][0]['total_days'],2)
    def test_private_paths_and_tokens_not_exported(self):
        got=public_methane({'status':'no_candidate','paths':{'result':'private'},'token':'secret','wind':{'source':'fixture','metadata_path':'private'}})
        self.assertNotIn('private',json.dumps(got));self.assertNotIn('secret',json.dumps(got))
    def test_export_retains_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            p=export_bundle(Path(folder)/'a.json')
            got=json.loads(p.read_text())
            self.assertIsNone(got['no2']);self.assertIsNone(got['methane'])
    def test_saved_result_has_real_original_location(self):
        m=json.loads((ROOT/'docs/data/demo.json').read_text(encoding='utf-8'))['methane']
        self.assertEqual(m['latitude'],23.86479);self.assertEqual(m['candidate_pixels'],0)
        self.assertAlmostEqual(m['common_valid_fraction'],.9604)
        self.assertTrue(m['current_acquired_at'].startswith('2026-09-22'))
        self.assertNotIn('paths',m)
    def test_notebook_is_valid_and_has_no_saved_errors(self):
        import nbformat
        nb=nbformat.read(ROOT/'Geoguard.ipynb',as_version=4);nbformat.validate(nb)
        for cell in nb.cells:
            if cell.cell_type=='code':
                ast.parse(cell.source)
                self.assertFalse(any(o.output_type=='error' for o in cell.outputs))
    def test_legacy_weights_are_still_pinned(self):
        text=(ROOT/'guided_colab/detection_helpers.py').read_text(encoding='utf-8')
        self.assertIn('be634fb9e24dc4877f44c1ff9f69972e6f0453e30d70c0dc03677876340ef246',text)
    def test_saved_no2_matches_raw_earthengine_export(self):
        raw=json.loads((ROOT/'sources/no2_earthengine_export.geojson').read_text(encoding='utf-8'))
        rows=unpack_stacked(raw['features'],'2026-01-01','2026-09-01')
        derived=summarize(rows,SITES,'2026-01-01','2026-09-01',5000,'COPERNICUS/S5P/NRTI/L3_NO2')
        saved=json.loads((ROOT/'docs/data/demo.json').read_text(encoding='utf-8'))['no2']
        self.assertEqual(saved['sites'],derived['sites'])
        self.assertEqual([s['valid_days'] for s in saved['sites']],[226,224])

if __name__=='__main__':unittest.main()
