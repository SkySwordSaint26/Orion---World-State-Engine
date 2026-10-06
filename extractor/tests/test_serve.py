"""The HTTP server (extractor/serve.py), with the pipeline stubbed out: no models needed."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from extractor import serve


def post(port, body, token="secret"):
    request = urllib.request.Request(f"http://127.0.0.1:{port}/extract", json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_extract_needs_the_token_and_returns_the_gold_document(monkeypatch):
    monkeypatch.setattr(serve, "extract", lambda story_id, text: {"story_id": story_id, "text": text})
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler("secret"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        assert post(port, {"story_id": "chapter_1", "text": "Dan waved."}) == \
            (200, {"story_id": "chapter_1", "text": "Dan waved."})
        assert post(port, {"story_id": "chapter_1", "text": "x"}, token="wrong")[0] == 401
        assert post(port, {"text": "no story id"})[0] == 400
        monkeypatch.setattr(serve, "extract", lambda story_id, text: 1 / 0)
        assert post(port, {"story_id": "chapter_1", "text": "x"}) == (500, {"error": "ZeroDivisionError: division by zero"})
    finally:
        server.shutdown()
