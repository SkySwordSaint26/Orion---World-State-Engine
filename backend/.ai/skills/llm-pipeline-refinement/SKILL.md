---
name: llm-pipeline-refinement
description: Recipe for tuning prompts, improving parser resilience, and upgrading LLM extraction models.
---

# Skill: LLM Pipeline Refinement

Follow this recipe when improving entity/relationship extraction accuracy, adjusting prompt rules, or integrating new model checkpoints.

---

## 1. Prompt Engineering Protocol

The extraction prompt is stored in [`app/pipeline/prompts/extraction_prompt.txt`](../../app/pipeline/prompts/extraction_prompt.txt).

### Best Practices:
1. **Few-Shot Grounding**: If the model frequently hallucinates inferred attributes (e.g. assuming an American setting when unstated), add explicit positive and negative few-shot contrastive examples.
2. **Strict Negative Constraints**: Reiterate: *"If an entity is merely discussed as a historical figure, do not extract them as an active event participant."*
3. **JSON Schema Adherence**: Remind the model: *"Output strictly valid JSON with no conversational prefix or markdown explanations."*

---

## 2. Testing Parser Robustness

When modifying [`app/pipeline/parsers/extraction_parser.py`](../../app/pipeline/parsers/extraction_parser.py):
1. Always test dirty inputs:
   - Markdown code block wrapped: ` ```json { ... } ``` `
   - Trailing commas: `{"entities": [1, 2, ], }`
   - Conversational preamble: `"Here is the extracted JSON: { ... }"`
2. Add the test case to [`app/tests/test_pipeline.py`](../../app/tests/test_pipeline.py).

---

## 3. Switching LLM Providers

In [`backend/.env`](../../.env), configure the active provider:

```env
# Local Ollama (Default)
LLM_PROVIDER="ollama"
OLLAMA_URL="http://localhost:11434/api/chat"
OLLAMA_MODEL="llama3.1:8b-instruct-q4_K_M"

# Cloud OpenAI
LLM_PROVIDER="openai"
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"

# Offline Deterministic Mock (for tests)
LLM_PROVIDER="mock"
```

The [`LLMClient`](../../app/pipeline/llm_client.py) never falls back automatically: if the configured provider fails, `LLMError` is raised and the extraction run is marked `failed`. The mock engine is used only when `LLM_PROVIDER="mock"` is set explicitly (a warning is logged), and must not be used with real world data.

---

## Verification

Run pipeline tests to ensure chunking, parsing, and clustering remain 100% functional:
```bash
PYTHONPATH=backend pytest app/tests/test_pipeline.py -v
```
