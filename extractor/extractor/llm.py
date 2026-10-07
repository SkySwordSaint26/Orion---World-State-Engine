"""The one LLM call: system + user prompt and an output format -> parsed JSON. Ollama constrains generation to the
format (a JSON schema, or "json" for any JSON object), so the reply always parses unless it was cut off, which raises
instead of returning partial data."""
import json
import os
import urllib.request
from typing import Any, Dict, Union

URL = "http://localhost:11434/api"
# NuExtract 2.0 4B, registered from its GGUF (requirements.txt); chosen in Phases 5 and 7. ORION_LLM_MODEL picks another
# Ollama model, e.g. the 8B on a bigger GPU (extractor/notebooks/kaggle_model_comparison.ipynb)
MODEL = os.environ.get("ORION_LLM_MODEL", "nuextract2-4b")
NUM_CTX = 4096                # a chunk prompt is well under this; a smaller cache leaves more VRAM for the weights


def _post(path: str, body: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    request = urllib.request.Request(f"{URL}/{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def generate(system: str, user: str, schema: Union[Dict[str, Any], str], num_predict: int = 1024,
             model: str = MODEL) -> Dict[str, Any]:
    body = {"model": model, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": num_predict},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    reply = _post("chat", body, 600)
    if reply.get("done_reason") == "length":
        raise RuntimeError(f"LLM reply cut off at num_predict={num_predict}")
    return json.loads(reply["message"]["content"])


def unload() -> None:
    """Free the VRAM of every model Ollama has loaded, now instead of after its 5-minute keep-alive: the encoders
    need it. Not only NuExtract: the backend's chat model (qwen2.5:7b, 4.7 GB) left loaded makes the encoders run
    out of memory on the 6 GB GPU."""
    with urllib.request.urlopen(f"{URL}/ps", timeout=10) as response:
        loaded = [m["name"] for m in json.load(response).get("models", [])]
    for name in loaded:
        _post("generate", {"model": name, "keep_alive": 0}, 60)
