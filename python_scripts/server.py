from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_scripts.client import ProviderError
from python_scripts.service import ProxyService


class ApiHandler(BaseHTTPRequestHandler):
    service = ProxyService()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send_json(200, {'ok': True})
            return
        if parsed.path == '/providers':
            self._send_json(200, {'providers': self.service.available_providers()})
            return
        if parsed.path.startswith('/providers/') and parsed.path.endswith('/models'):
            provider = parsed.path.split('/')[2]
            try:
                models = self.service.list_models(provider)
                self._send_json(200, {'provider': provider, 'models': models})
            except ProviderError as exc:
                self._send_json(400, {'ok': False, 'error': str(exc)})
            return
        self._send_json(404, {'ok': False, 'error': 'not found'})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(length) if length > 0 else b'{}'
        try:
            payload = json.loads(body.decode('utf-8')) if body else {}
        except json.JSONDecodeError:
            self._send_json(400, {'ok': False, 'error': 'invalid json'})
            return

        if parsed.path.startswith('/providers/') and parsed.path.endswith('/probe'):
            provider = parsed.path.split('/')[2]
            model = str(payload.get('model', '')).strip()
            if not model:
                self._send_json(400, {'ok': False, 'error': 'missing model'})
                return
            result = self.service.probe(provider, model)
            self._send_json(200 if result.ok else 400, result.__dict__)
            return

        if parsed.path == '/chat/completions':
            provider = str(payload.get('provider', '')).strip()
            model = str(payload.get('model', '')).strip()
            if not provider or not model:
                self._send_json(400, {'ok': False, 'error': 'missing provider or model'})
                return
            result = self.service.probe(provider, model)
            if result.ok:
                self._send_json(200, {'ok': True, 'provider': provider, 'model': model, 'content': result.content})
            else:
                self._send_json(400, {'ok': False, 'provider': provider, 'model': model, 'error': result.error})
            return

        self._send_json(404, {'ok': False, 'error': 'not found'})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def run(host: str = '127.0.0.1', port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f'Python backend listening on http://{host}:{port}')
    server.serve_forever()


if __name__ == '__main__':
    run()
