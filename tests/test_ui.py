"""Optional widget integration tests; no fabricated values become demo data."""
import importlib.util
import tempfile
import unittest

HAS_UI=all(importlib.util.find_spec(x) for x in ['ipyleaflet','ipywidgets','pyproj'])

@unittest.skipUnless(HAS_UI,'Notebook dependencies are optional in lightweight CI')
class WidgetTests(unittest.TestCase):
    def setUp(self):
        from geoguard.notebook_ui import CombinedLab
        self.temp=tempfile.TemporaryDirectory()
        self.lab=CombinedLab(self.temp.name,engine=object())
    def tearDown(self):
        self.lab.close();self.temp.cleanup()
    def test_one_shared_location(self):
        self.lab.presets.value='jebel-ali'
        self.assertEqual(self.lab.lat.value,25.0083)
        self.assertEqual(self.lab.no2_circle.location,[25.0083,55.0875])
    def test_changed_location_clears_both_results(self):
        self.lab.result={'status':'candidate'};self.lab.no2_result={'status':'ready'}
        self.lab.lat.value=25.3
        self.assertIsNone(self.lab.result);self.assertIsNone(self.lab.no2_result)
    def test_missing_auth_does_not_fabricate_data(self):
        self.lab.calculate_no2()
        self.assertIsNone(self.lab.no2_result)
        self.assertIn('project ID',self.lab.no2_status.value)
    def test_metric_switch_preserves_evidence_and_location_clears(self):
        self.lab.load_no2_example()
        self.lab.metric.value='CH4'
        self.assertEqual(self.lab.product.value,'OFFL')
        self.assertEqual(list(self.lab.product.options),['OFFL'])
        self.assertIn('ppb',self.lab.no2_status.value)
        self.assertIsNotNone(self.lab.no2_result)
        self.assertEqual(set(self.lab.measurements),{'CO','SO2','CH4'})
        self.lab.lat.value=25.3
        self.assertEqual(self.lab.measurements,{})
        self.assertIsNone(self.lab.no2_result)

if __name__=='__main__':unittest.main()
