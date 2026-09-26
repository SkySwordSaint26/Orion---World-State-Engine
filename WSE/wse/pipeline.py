"""Runs the extraction stages in order on one story and returns its gold document."""
import gc
from typing import Any, Callable, Dict, Tuple

from app.contracts.gold import GOLD_SCHEMA_VERSION
from app.evaluation.schema import load_schema, schema_errors
from wse import coref as coref_module, llm, mentions as mentions_module
from wse.coref import coref
from wse.events import events
from wse.mentions import mentions
from wse.relations import relations
from wse.temporal import temporal

_SCHEMA = load_schema()
LISTS = tuple(k for k in _SCHEMA["required"] if _SCHEMA["properties"][k].get("type") == "array")

def release_encoders(doc: Dict[str, Any]) -> None:
    """The 6 GB GPU holds the encoder models or the LLM, not both: drop the encoders before the LLM stages."""
    # ponytail: encoders reload for every story (~30 s); run stories stage by stage if throughput matters
    import torch
    mentions_module._gliner.cache_clear()
    coref_module._booknlp.cache_clear()
    gc.collect()
    torch.cuda.empty_cache()


def release_llm(doc: Dict[str, Any]) -> None:
    """...and hand the GPU back to the encoders for the next story (Ollama would keep the model for 5 minutes)."""
    llm.unload()


# Each stage appends to the document's lists in place; stages are added phase by phase (see the plan).
STAGES: Tuple[Callable[[Dict[str, Any]], None], ...] = (mentions, coref, events, temporal, release_encoders,
                                                        relations, release_llm)


def extract(story_id: str, text: str) -> Dict[str, Any]:
    doc = {"schema_version": GOLD_SCHEMA_VERSION, "story_id": story_id, "text": text, **{k: [] for k in LISTS}}
    for stage in STAGES:
        stage(doc)
    errors = schema_errors(doc)
    if errors:
        raise ValueError(f"{story_id}: output violates the gold schema: {errors[:5]}")
    return doc
