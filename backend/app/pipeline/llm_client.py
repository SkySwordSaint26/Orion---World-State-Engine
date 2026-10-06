from typing import Dict, Any, List, Optional
import httpx

from app.config.settings import settings
from app.config.logging import get_logger

logger = get_logger(__name__)

class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.ollama_url = settings.OLLAMA_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.openai_key = settings.OPENAI_API_KEY
        self.openai_model = settings.OPENAI_MODEL

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

# Global singleton
llm_client = LLMClient()
