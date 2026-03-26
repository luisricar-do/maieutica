"""Configuração Azure OpenAI partilhada pelo índice RAG e pelo grafo."""

from __future__ import annotations

import os


def azure_openai_api_key() -> str | None:
    return (
        os.environ.get("AZURE_OPENAI_KEY")
        or os.environ.get("AZURE_OPENAI_API_KEY")
        or None
    )
