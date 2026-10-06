"""
The pipeline over HTTP, so the backend can extract on a remote GPU (notebooks/kaggle_extractor_server.ipynb, behind
an ngrok tunnel). The models stay loaded between requests.

    POST /extract  {"story_id": "...", "text": "..."}  ->  the gold document (what `run` writes)
    GET  /health                                       ->  {"model": the Ollama model}

/extract needs `Authorization: Bearer $ORION_EXTRACTOR_TOKEN`: the tunnel makes this a public URL.
"""
import hmac
import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from extractor import llm
from extractor.pipeline import extract

_gpu = threading.Lock()          # one extraction at a time: the stages share the GPU and free it between them


def make_handler(token: str):
    expected = f"Bearer {token}".encode()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: Dict[str, Any]) -> None:
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                return self._reply(200, {"model": llm.MODEL})
            self._reply(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/extract":
                return self._reply(404, {"error": "not found"})
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected):
                return self._reply(401, {"error": "missing or wrong bearer token"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                story_id, text = body["story_id"], body["text"]
                assert isinstance(story_id, str) and isinstance(text, str)
            except (ValueError, KeyError, TypeError, AssertionError):
                return self._reply(400, {"error": 'expected JSON {"story_id": str, "text": str}'})
            try:
                with _gpu:
                    doc = extract(story_id, text)
            except Exception as e:
                traceback.print_exc()
                return self._reply(500, {"error": f"{type(e).__name__}: {e}"})
            self._reply(200, doc)

    return Handler


def serve(port: int, host: str = "127.0.0.1") -> None:
    token = os.environ.get("ORION_EXTRACTOR_TOKEN", "")
    if not token:
        raise SystemExit("set ORION_EXTRACTOR_TOKEN: the server refuses to run without one")
    print(f"extractor serving on http://{host}:{port} with {llm.MODEL}", flush=True)
    ThreadingHTTPServer((host, port), make_handler(token)).serve_forever()
