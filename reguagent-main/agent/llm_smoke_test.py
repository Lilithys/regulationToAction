#!/usr/bin/env python3
"""Manual connectivity check -- needs a real key and network, so it's not part of
the offline unittest suite. Run after configuring a provider, either via
agent/configure_llm.py --from-env --provider {deepseek,openai} (writes .env.local),
or by exporting variables directly in this terminal:

  # Anthropic, or any Anthropic-Messages-API-compatible endpoint (e.g. DeepSeek):
  export ANTHROPIC_API_KEY=sk-...            # real Anthropic
  # or: export LLM_API_KEY=... ; export LLM_BASE_URL=https://api.deepseek.com/anthropic ; export LLM_MODEL=deepseek-v4-flash

  # OpenAI:
  export LLM_PROVIDER=openai
  export OPENAI_API_KEY=sk-...               # or LLM_API_KEY
  export LLM_MODEL=gpt-5                     # check OpenAI's current docs for the live name

  .venv/bin/python agent/llm_smoke_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import complete

if __name__ == '__main__':
    reply = complete(
        system='Reply with exactly one word.',
        user='What is the capital of Ireland?')
    print('Model replied:', reply.strip())
