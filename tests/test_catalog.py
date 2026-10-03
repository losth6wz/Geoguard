import unittest
from unittest.mock import Mock, patch
import requests
from live_detection.acquisition import discover, CatalogUnavailable, BACKUP_CATALOG

PRODUCT='S2B_MSIL1C_20260929T064629_N0513_R020_T40RCN_20260929T103842'


def response(data=None, invalid=False):
    r=Mock(url=BACKUP_CATALOG)
    r.raise_for_status.return_value=None
    if invalid:r.json.side_effect=ValueError('HTML response')
    else:r.json.return_value=data
    return r


class CatalogTests(unittest.TestCase):
    def test_html_falls_back_preserving_safe_identity(self):
        feature={'id':'S2B_40RCN_20260929_0_L1C','geometry':{'type':'Polygon','coordinates':[]},
                 'properties':{'datetime':'2026-09-29T07:02:40Z','s2:product_uri':PRODUCT+'.SAFE'}}
        with patch('live_detection.acquisition.requests.get',side_effect=[response(invalid=True),response({'features':[feature]})]) as get:
            results=discover(25.2048,55.2708,as_of='2026-10-04T00:00:00Z')
        self.assertEqual(results[0]['id'],PRODUCT)
        self.assertTrue(results[0]['catalog_fallback_used'])
        self.assertIsNone(results[0]['available_at'])
        self.assertEqual(get.call_args_list[0].kwargs['params'],get.call_args_list[1].kwargs['params'])

    def test_both_unavailable_is_not_empty_observation(self):
        with patch('live_detection.acquisition.requests.get',side_effect=requests.Timeout()):
            with self.assertRaisesRegex(CatalogUnavailable,'Both satellite catalogues'):
                discover(25.2,55.2)

    def test_empty_valid_primary_does_not_fabricate_fallback(self):
        with patch('live_detection.acquisition.requests.get',return_value=response({'features':[]})) as get:
            self.assertEqual(discover(25.2,55.2),[])
            self.assertEqual(get.call_count,1)

    def test_backup_never_substitutes_l2a(self):
        feature={'id':'x','properties':{'s2:product_uri':PRODUCT.replace('MSIL1C','MSIL2A')+'.SAFE'}}
        with patch('live_detection.acquisition.requests.get',side_effect=[response(invalid=True),response({'features':[feature]})]):
            with self.assertRaisesRegex(CatalogUnavailable,'processing level'):
                discover(25.2,55.2)
