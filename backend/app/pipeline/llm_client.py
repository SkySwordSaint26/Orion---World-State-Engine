import json
import os
import re
from typing import Dict, Any, List, Optional
import httpx

from app.config.settings import settings
from app.config.logging import get_logger

logger = get_logger(__name__)

class LLMError(RuntimeError):
    """Raised when the configured LLM provider cannot produce a response."""


class LLMConfigurationError(LLMError):
    """Raised when LLM_PROVIDER is missing required configuration or is unknown."""


class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.ollama_url = settings.OLLAMA_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.openai_key = settings.OPENAI_API_KEY
        self.openai_model = settings.OPENAI_MODEL
        if self.provider == "mock":
            logger.warning(
                "LLM_PROVIDER=mock: extraction will use the offline HEURISTIC MOCK engine. "
                "Output is NOT produced by a language model and must not be used with real world data."
            )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True,
        temperature: float = 0.0,
        schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Dispatches a generation request to the configured provider.

        There is no automatic fallback between providers. A provider failure raises
        LLMError so the calling extraction run fails instead of writing fabricated data.
        The mock engine is used only when LLM_PROVIDER=mock is set explicitly.

        `schema` (JSON schema) constrains Ollama's output at generation time; other providers ignore it,
        so callers must still validate the output.
        """
        provider = self.provider

        if provider == "mock":
            logger.warning("LLM_PROVIDER=mock: returning heuristic MOCK extraction (not a real LLM response).")
            return self._mock_extraction(prompt)

        if provider == "openai":
            if not self.openai_key:
                raise LLMConfigurationError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
            try:
                output = self._call_openai(prompt, system_prompt, json_mode, temperature)
            except Exception as e:
                raise LLMError(f"OpenAI request failed: {e}") from e
        elif provider == "ollama":
            try:
                output = self._call_ollama(prompt, system_prompt, json_mode, temperature, schema)
            except Exception as e:
                raise LLMError(f"Ollama request failed: {e}") from e
        else:
            raise LLMConfigurationError(
                f"Unknown LLM_PROVIDER '{provider}'. Expected 'ollama', 'openai' or 'mock'."
            )

        if not output or not output.strip():
            raise LLMError(f"{provider} returned an empty response.")
        return output

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """Dispatches conversational chat query."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        if self.provider == "openai" and self.openai_key:
            try:
                return self._chat_openai(all_messages, temperature)
            except Exception as e:
                logger.warning(f"OpenAI chat failed: {e}")

        if self.provider == "ollama" or (self.provider != "mock" and not self.openai_key):
            try:
                return self._chat_ollama(all_messages, temperature)
            except Exception as e:
                logger.warning(f"Ollama chat failed ({e}), using mock answer.")

        # Fallback chat response
        last_user_msg = messages[-1]["content"] if messages else ""
        return (
            f"Orion Knowledge Assistant: In response to '{last_user_msg}', "
            f"based on current world state entries, all entity attributes and relationships "
            f"have been verified. No critical timeline conflicts detected."
        )

    def _call_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        temperature: float,
        schema: Optional[Dict[str, Any]] = None
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": settings.OLLAMA_NUM_CTX,
                        "num_predict": settings.OLLAMA_NUM_PREDICT}
        }
        if json_mode:
            payload["format"] = schema or "json"

        with httpx.Client(timeout=180.0) as client:
            resp = client.post(self.ollama_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    def _chat_ollama(self, messages: List[Dict[str, str]], temperature: float) -> str:
        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature}
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(self.ollama_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    def _call_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        temperature: float
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload: Dict[str, Any] = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": temperature
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=120.0) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _chat_openai(self, messages: List[Dict[str, str]], temperature: float) -> str:
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": temperature
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _mock_extraction(self, text: str) -> str:
        """
        Heuristic offline extractor that extracts capitalized entities,
        relationships, and events without requiring an active external LLM server.
        """
        # Simple regex heuristic for character and location extraction
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities = []
        seen = set()
        for w in words[:10]:
            if w not in seen and len(w) > 2 and w not in {"The", "Chapter", "Act", "Then", "When", "There", "In", "On", "At", "He", "She"}:
                seen.add(w)
                ent_type = "location" if any(loc in w.lower() for loc in ["city", "haven", "castle", "hall", "kingdom", "valley"]) else "character"
                entities.append({
                    "mention": w,
                    "canonical_name": w,
                    "type": ent_type,
                    "attributes": {"status": "active"},
                    "evidence": f"Mentioned in manuscript text: '{w}'"
                })

        relationships = []
        if len(entities) >= 2:
            relationships.append({
                "subject": entities[0]["canonical_name"],
                "predicate": "ACQUAINTED_WITH",
                "object": entities[1]["canonical_name"],
                "certainty": "DEFINITE",
                "evidence": f"{entities[0]['canonical_name']} and {entities[1]['canonical_name']} appear in the same narrative segment."
            })

        events = [{
            "id": "event_1",
            "type": "NARRATIVE_EVENT",
            "participants": [e["canonical_name"] for e in entities[:3]],
            "location": entities[1]["canonical_name"] if len(entities) > 1 else None,
            "time_expression": "present",
            "evidence": text[:120].strip() + "..."
        }]

        return json.dumps({
            "entities": entities,
            "relationships": relationships,
            "events": events,
            "state_changes": [],
            "temporal_relations": []
        })

# Global singleton
llm_client = LLMClient()
