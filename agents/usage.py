"""
Contagem de tokens de um turno, somada sobre todas as chamadas ao modelo.

A condição A do Capítulo 4 não é uma chamada: o turno passa pelo roteador, pelo analista, pelo
estrategista e pelo comunicador. O custo do turno é a soma das quatro, e é isso que se compara
com a chamada única das condições B e C.

Recolhe-se por *callback* do LangChain, entregue ao grafo em ``ainvoke(..., config=...)``: nenhum
agente precisa de saber que está a ser medido, e o grafo fica intacto.
"""

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


def zero_usage() -> dict[str, int]:
    return {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0}


def usage_from_response(response: Any) -> dict[str, int]:
    """Tokens de uma resposta do modelo; zeros quando o proxy não os reporta."""
    meta = getattr(response, "usage_metadata", None)
    if isinstance(meta, dict) and meta:
        return {
            "promptTokens": int(meta.get("input_tokens") or 0),
            "completionTokens": int(meta.get("output_tokens") or 0),
            "totalTokens": int(meta.get("total_tokens") or 0),
        }
    token_usage = (getattr(response, "response_metadata", None) or {}).get(
        "token_usage"
    ) or {}
    return {
        "promptTokens": int(token_usage.get("prompt_tokens") or 0),
        "completionTokens": int(token_usage.get("completion_tokens") or 0),
        "totalTokens": int(token_usage.get("total_tokens") or 0),
    }


class TokenUsageCollector(BaseCallbackHandler):
    """Soma os tokens de todas as chamadas ao modelo dentro de um turno.

    ``calls`` conta as chamadas observadas: um turno da condição A com ``calls`` 1 indica que
    alguma etapa do grafo não reportou uso, e a soma está subestimada.
    """

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.calls = 0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = self._from_llm_result(response)
        if usage is None:
            return
        self.calls += 1
        self.prompt_tokens += usage["promptTokens"]
        self.completion_tokens += usage["completionTokens"]
        self.total_tokens += usage["totalTokens"]

    @staticmethod
    def _from_llm_result(response: Any) -> dict[str, int] | None:
        """``LLMResult``: o total vem em ``llm_output``; em stream, da mensagem gerada."""
        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage") or {}
        if token_usage:
            return {
                "promptTokens": int(token_usage.get("prompt_tokens") or 0),
                "completionTokens": int(token_usage.get("completion_tokens") or 0),
                "totalTokens": int(token_usage.get("total_tokens") or 0),
            }
        for lote in getattr(response, "generations", None) or []:
            for generation in lote or []:
                message = getattr(generation, "message", None)
                meta = getattr(message, "usage_metadata", None)
                if isinstance(meta, dict) and meta:
                    return {
                        "promptTokens": int(meta.get("input_tokens") or 0),
                        "completionTokens": int(meta.get("output_tokens") or 0),
                        "totalTokens": int(meta.get("total_tokens") or 0),
                    }
        return None

    def as_dict(self) -> dict[str, int]:
        return {
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": self.total_tokens,
            "calls": self.calls,
        }
