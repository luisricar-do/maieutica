"""As três condições da bancada (Seção 4.3.2 da dissertação).

**A** é o artefato: o grafo roteador, analista, estrategista e comunicador, acionado por
``POST /api/help``. **B** é a ablação da arquitetura e **C** a referência descritiva: uma única
chamada ao mesmo modelo, pelo mesmo proxy, em ``POST /api/help/single`` — B com o prompt
socrático, C com a instrução neutra de assistente de programação.

As três saem do **mesmo serviço**, com o mesmo corpo de pedido e o mesmo registro por turno: a
comparação não pode ser confundida por diferença de infraestrutura. O prompt de cada variante e
o molde de contexto vivem no serviço, congelados e com SHA-256 próprio — o harness não monta
prompt nenhum; lê os hashes de ``GET /api/help/single/prompts`` e grava-os no manifesto.

Nenhuma das três recebe ``bug_desc``: o artefato não a tem em produção e dá-la às outras
confundiria a leitura. B e C também não recebem ``hintLevel``, ``previousCode`` nem
``previousErrors`` no prompt — o serviço aceita-os no contrato e ignora-os.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from avaliacao import http
from avaliacao.config import Config
from avaliacao.itens import Prefixo

#: Variante de prompt do serviço por condição de chamada única.
VARIANTE_POR_CONDICAO = {"B": "socratic", "C": "neutral"}

CONDICOES = ("A", "B", "C")

#: B é a ablação da política sob pressão: só os prefixos que exercem pedido explícito.
CONDICOES_SO_PRESSAO = ("B",)


def session_id(prefixo_id: str, condicao: str, execucao: int) -> str:
    """``sessionId`` válido para o serviço (``^[A-Za-z0-9_-]{1,64}$``) e estável por chamada."""
    digest = hashlib.sha1(prefixo_id.encode("utf-8")).hexdigest()[:16]
    return f"bancada-{digest}-{condicao.lower()}-{execucao}"


def payload_a(prefixo: Prefixo, execucao: int) -> dict[str, Any]:
    """Corpo de ``POST /api/help`` (Subseção 4.3.2: nível de dica 1, documentação desligada)."""
    corpo: dict[str, Any] = {
        "code": prefixo.code,
        "errors": list(prefixo.errors),
        "compilerErrorLines": list(prefixo.compiler_error_lines),
        "history": list(prefixo.history),
        "problemStatement": prefixo.problem_statement,
        "hintLevel": 1,
        "includeDocumentation": False,
        "sessionId": session_id(prefixo.id, "A", execucao),
    }
    if prefixo.previous_code is not None:
        corpo["previousCode"] = prefixo.previous_code
        corpo["previousErrors"] = list(prefixo.previous_errors or [])
    return corpo


def payload_single(prefixo: Prefixo, execucao: int, condicao: str) -> dict[str, Any]:
    """Corpo de ``POST /api/help/single``: o mesmo de A, mais ``promptVariant``.

    Manter o corpo idêntico é deliberado — o que distingue as condições é o que o serviço faz
    com ele, não o que o harness envia.
    """
    corpo = payload_a(prefixo, execucao)
    corpo["sessionId"] = session_id(prefixo.id, condicao, execucao)
    corpo["promptVariant"] = VARIANTE_POR_CONDICAO[condicao]
    return corpo


def hashes_do_servico(cfg: Config) -> dict[str, str]:
    """Hashes dos prompts congelados e do molde, lidos do serviço que vai correr a bancada.

    É a conferência que antecede a corrida: se algum hash mudou desde a corrida anterior, o
    prompt mudou e as duas corridas não são comparáveis.
    """
    resposta = http.get_json(
        f"{cfg.api_base.rstrip('/')}/help/single/prompts", timeout=cfg.timeout_s
    )
    if not resposta.ok:
        raise SystemExit(
            f"não foi possível ler os prompts do serviço ({resposta.erro or resposta.status}). "
            "Suba o serviço com `make start` antes de rodar a bancada."
        )
    try:
        corpo = resposta.json()
        return {
            "prompt_socratic": corpo["prompts"]["socratic"]["sha256"],
            "prompt_neutral": corpo["prompts"]["neutral"]["sha256"],
            "contexto": corpo["context"]["sha256"],
        }
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"resposta inesperada de /help/single/prompts: {exc}") from exc


def executar_a(cfg: Config, prefixo: Prefixo, execucao: int) -> dict[str, Any]:
    resposta = http.post_json(
        f"{cfg.api_base.rstrip('/')}/help",
        payload_a(prefixo, execucao),
        timeout=cfg.timeout_s,
    )
    base = _base(resposta, "A", execucao)
    if not resposta.ok:
        base["erro"] = resposta.erro or f"HTTP {resposta.status}"
        return base
    try:
        corpo = resposta.json()
    except ValueError as exc:
        base["erro"] = f"resposta não-JSON: {exc}"
        return base
    meta = corpo.get("tutorMeta") or {}
    base.update(
        {
            "message": corpo.get("message", ""),
            "diagnosis": corpo.get("diagnosis"),
            "actions": corpo.get("actions", []),
            "tutorMeta": meta,
            "modelo": meta.get("model", ""),
            "intent": meta.get("intent", ""),
            "movimento_runtime": meta.get("studentMovement", ""),
            # Soma das chamadas do grafo no turno, comparável com a chamada única de B e C.
            "tokens": meta.get("usage", {}) or {},
        }
    )
    return base


def executar_single(
    cfg: Config, prefixo: Prefixo, execucao: int, condicao: str
) -> dict[str, Any]:
    """Uma chamada a ``POST /api/help/single`` na variante da condição."""
    resposta = http.post_json(
        f"{cfg.api_base.rstrip('/')}/help/single",
        payload_single(prefixo, execucao, condicao),
        timeout=cfg.timeout_s,
    )
    base = _base(resposta, condicao, execucao)
    if not resposta.ok:
        base["erro"] = resposta.erro or f"HTTP {resposta.status}"
        return base
    try:
        corpo = resposta.json()
    except ValueError as exc:
        base["erro"] = f"resposta não-JSON: {exc}"
        return base
    meta = corpo.get("tutorMeta") or {}
    base.update(
        {
            "message": corpo.get("message", ""),
            "actions": corpo.get("actions", []),
            "tutorMeta": meta,
            "modelo": meta.get("model", ""),
            "tokens": meta.get("usage", {}) or {},
            "finish_reason": meta.get("finishReason", ""),
            "prompt_variant": meta.get("promptVariant", ""),
            "prompt_sha256": meta.get("promptSha256", ""),
            "context_sha256": meta.get("contextSha256", ""),
        }
    )
    return base


def executar_b(cfg: Config, prefixo: Prefixo, execucao: int) -> dict[str, Any]:
    return executar_single(cfg, prefixo, execucao, "B")


def executar_c(cfg: Config, prefixo: Prefixo, execucao: int) -> dict[str, Any]:
    return executar_single(cfg, prefixo, execucao, "C")


def _base(resposta: http.Resposta, condicao: str, execucao: int) -> dict[str, Any]:
    return {
        "condicao": condicao,
        "execucao": execucao,
        "ts": datetime.now(UTC).isoformat(),
        "latencia_ms": resposta.latencia_ms,
        "http_status": resposta.status,
        "message": "",
        "diagnosis": None,
        "actions": [],
        "tutorMeta": None,
        "modelo": "",
        "tokens": {},
        "finish_reason": "",
        "erro": "",
    }
