"""The one LLM call: system + user prompt and an output format -> parsed JSON. Ollama constrains generation to the
format (a JSON schema, or "json" for any JSON object), so the reply always parses unless it was cut off, which raises
instead of returning partial data."""
import json
import urllib.request
from typing import Any, Dict, Union

URL = "http://localhost:11434/api"
MODEL = "nuextract2-4b"       # NuExtract 2.0 4B, registered from its GGUF (requirements.txt); chosen in Phases 5 and 7
NUM_CTX = 4096                # a chunk prompt is well under this; a smaller cache leaves more VRAM for the weights


def _post(path: str, body: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    request = urllib.request.Request(f"{URL}/{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def generate(system: str, user: str, schema: Union[Dict[str, Any], str], num_predict: int = 1024) -> Dict[str, Any]:
    body = {"model": MODEL, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": num_predict},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    reply = _post("chat", body, 600)
    if reply.get("done_reason") == "length":
        raise RuntimeError(f"LLM reply cut off at num_predict={num_predict}")
    return json.loads(reply["message"]["content"])


def unload() -> None:
    """Free the model's VRAM now instead of after Ollama's 5-minute keep-alive (the encoders need it back)."""
    _post("generate", {"model": MODEL, "keep_alive": 0}, 60)
