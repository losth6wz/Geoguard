"""Local, same-origin website and asynchronous methane screening service.

Run: python -m geoguard.server. Binds only to loopback; not a public deployment.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from threading import Lock
from urllib.parse import urlsplit

from .core import bundle, public_methane, validate_location

ROOT = Path(__file__).resolve().parents[1]
COLAB_PROXY_V4 = True


class Jobs:
    def __init__(self, engine=None):
        self.engine = engine
        self.items = {}
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, latitude, longitude):
        lat, lon = validate_location(latitude, longitude)
        with self.lock:
            if any(j['state'] == 'running' for j in self.items.values()):
                raise RuntimeError('A check is already running. Wait for it to finish.')
            if len(self.items) >= 30:
                self.items.pop(next(iter(self.items)))
            ident = secrets.token_hex(16)
            self.items[ident] = dict(state='running', message='Starting satellite check…', latitude=lat, longitude=lon)
        self.pool.submit(self.run, ident, lat, lon)
        return ident

    def run(self, ident, lat, lon):
        def update(**fields):
            with self.lock:
                self.items[ident].update(fields)
        try:
            if self.engine is None:
                from live_detection.engine import LatestDetector
                self.engine = LatestDetector(ROOT / 'runtime/web')
            result = self.engine.run(lat, lon, progress=lambda message: update(message=message))
            figure = None
            path = (result.get('paths') or {}).get('figure')
            if path:
                p = Path(path).resolve()
                if p.is_relative_to(self.engine.root) and p.is_file() and p.stat().st_size < 8*1024*1024:
                    figure = 'data:image/png;base64,' + base64.b64encode(p.read_bytes()).decode()
            evidence = bundle(methane=public_methane({**result, 'latitude': lat, 'longitude': lon}, figure))
            update(state='done', message=result.get('message', 'Check complete.'), result=evidence)
        except Exception as exc:
            import logging
            logging.exception('Methane check failed')
            from live_detection.acquisition import CatalogUnavailable
            message = str(exc) if isinstance(exc,CatalogUnavailable) else 'The satellite check failed ('+type(exc).__name__+'). No detection result was produced.'
            update(state='error', message=message)

    def get(self, ident):
        with self.lock:
            return dict(self.items[ident]) if ident in self.items else None


def make_server(port=8768, jobs=None, proxy_host=None):
    jobs = jobs or Jobs()
    token = secrets.token_urlsafe(32)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT / 'docs'), **kwargs)

        def allowed_host(self):
            # Colab authenticates its output proxy and rewrites Host internally.
            # Only start_demo's Colab branch enables this mode; binding remains
            # loopback-only and mutation requests still require a session token.
            if proxy_host:
                return True
            return self.headers.get('Host') in tuple(filter(None, (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}', proxy_host)))

        def reply(self, status, value):
            raw = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {'error': 'Invalid host'})
            path = urlsplit(self.path).path
            if path == '/api/config':
                return self.reply(200, {'token': token, 'mode': 'local', 'model': 'MARS-S2L'})
            if path.startswith('/api/jobs/'):
                if not secrets.compare_digest(self.headers.get('X-Geoguard-Token', ''), token):
                    return self.reply(403, {'error': 'Open this service website to connect.'})
                job = jobs.get(path.rsplit('/', 1)[-1])
                return self.reply(200 if job else 404, job or {'error': 'Job not found; the service may have restarted.'})
            if path.startswith('/api/'):
                return self.reply(404, {'error': 'Unknown endpoint'})
            super().do_GET()

        def do_POST(self):
            if not self.allowed_host() or not secrets.compare_digest(self.headers.get('X-Geoguard-Token', ''), token):
                return self.reply(403, {'error': 'Open this service website to connect.'})
            if self.path != '/api/jobs':
                return self.reply(404, {'error': 'Unknown endpoint'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                ident = jobs.submit(payload['latitude'], payload['longitude'])
                self.reply(202, {'id': ident})
            except RuntimeError as exc:
                self.reply(409, {'error': str(exc)})
            except (ValueError, TypeError, KeyError):
                self.reply(400, {'error': 'Supply valid UAE latitude and longitude.'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


_service = None


def start_demo():
    """Serve the live website within Colab's authenticated output frame."""
    global _service
    from threading import Thread
    try:
        from google.colab import output
    except ImportError:
        output = None
    if _service is None:
        proxy_host = None
        if output:
            proxy_host = urlsplit(output.eval_js('google.colab.kernel.proxyPort(8768)')).netloc
        _service = make_server(proxy_host=proxy_host)
        Thread(target=_service.serve_forever, daemon=True).start()
    if output:
        output.serve_kernel_port_as_iframe(8768, height=1100, cache_in_notebook=False)
    else:
        from IPython.display import display, HTML
        display(HTML('<a href="http://127.0.0.1:8768" target="_blank">Open connected GeoGuard demo</a>'))


if __name__ == '__main__':
    service = make_server()
    print('GeoGuard AI service: http://127.0.0.1:8768', flush=True)
    service.serve_forever()
