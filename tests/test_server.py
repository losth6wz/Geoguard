import json
from pathlib import Path
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from geoguard.server import Jobs, make_server


class Engine:
    root = Path('/unused')
    def run(self, latitude, longitude, progress):
        progress('Testing job transport')
        return {'status': 'not_assessable', 'message': 'Test input only', 'paths': {}, 'private_key': 'never-export'}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.jobs = Jobs(Engine())
        self.server = make_server(0, self.jobs)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.token = self.request('/api/config')['token']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.jobs.pool.shutdown()

    def request(self, path, value=None, token=None):
        request = Request(self.base+path, data=json.dumps(value).encode() if value is not None else None,
                          headers={'Content-Type':'application/json', 'X-Geoguard-Token':token or ''})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_job_returns_selected_coordinates_without_private_fields(self):
        job = self.request('/api/jobs', {'latitude':24.5,'longitude':54.5}, self.token)
        for _ in range(100):
            state = self.request('/api/jobs/'+job['id'], token=self.token)
            if state['state'] == 'done': break
            time.sleep(.01)
        self.assertEqual(state['state'], 'done')
        self.assertEqual(state['result']['methane']['latitude'],24.5)
        self.assertNotIn('private_key',str(state))
        self.assertNotIn('paths',state['result']['methane'])

    def test_missing_token_rejected(self):
        with self.assertRaises(HTTPError) as err:
            self.request('/api/jobs', {'latitude':24.5,'longitude':54.5})
        self.assertEqual(err.exception.code,403)

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(HTTPError) as err:
            self.request('/api/jobs', {'latitude':0,'longitude':0}, self.token)
        self.assertEqual(err.exception.code,400)

    def test_busy_rejected(self):
        self.jobs.items['busy'] = {'state':'running'}
        with self.assertRaises(HTTPError) as err:
            self.request('/api/jobs', {'latitude':24.5,'longitude':54.5}, self.token)
        self.assertEqual(err.exception.code,409)

    def test_bad_host_rejected(self):
        with self.assertRaises(HTTPError) as err:
            urlopen(Request(self.base+'/api/config',headers={'Host':'untrusted.example'}))
        self.assertEqual(err.exception.code,403)
