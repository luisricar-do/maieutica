"""Juiz automático (Subseção 4.3.4 da dissertação).

Modelo de linguagem de **família distinta** da do modelo que anima o tutor — Gemini, da Google —,
com temperatura zero e **sem receber a condição de origem**, para neutralizar a auto-preferência
documentada por Zheng et al. (2023). O prompt reproduz literalmente as definições operacionais dos
apêndices de rubrica e de diretividade (``prompts/juiz.md``).

O que o protocolo fixa é a família do modelo, não o caminho até ele: o juiz pode ser acionado
pelo mesmo *proxy* LiteLLM do tutor (``JUIZ_PROVEDOR=litellm``, a mesma autenticação) ou pela API
da Google (``JUIZ_PROVEDOR=gemini``, com ``GEMINI_API_KEY``). O que não serve é juiz da **mesma
família** do tutor; ``familia_do_modelo`` existe para essa verificação, feita antes de julgar.

O juiz classifica tanto os turnos gerados quanto os **turnos de referência** do banco: são estes
que dão o ``d_{k-1}`` da taxa de contingência em bancada e a calibração interna dos limiares.

A classificação só é reportada depois de validada contra codificação humana em subamostra
(comandos ``amostra-humana`` e ``kappa``).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from avaliacao import http
from avaliacao.config import PROMPTS_DIR, Config, sha256_texto

MOVIMENTOS_JUIZ = ("PROGRESSO", "ESTAGNACAO", "REGRESSAO", "PEDIDO_EXPLICITO", "NENHUM")
ANCORAGENS = ("sim", "nao", "alvo_errado")
FALHAS = ("irrelevante", "repetida", "excessivamente_direta", "prematura")

ESQUEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "diretividade": {"type": "integer"},
        "movimento_estudante": {"type": "string", "enum": list(MOVIMENTOS_JUIZ)},
        "fidelidade": {"type": "integer"},
        "falhas": {
            "type": "object",
            "properties": {nome: {"type": "boolean"} for nome in FALHAS},
            "required": list(FALHAS),
        },
        "ancorado": {"type": "string", "enum": list(ANCORAGENS)},
        "justificativa": {"type": "string"},
    },
    "required": [
        "diretividade",
        "movimento_estudante",
        "fidelidade",
        "falhas",
        "ancorado",
        "justificativa",
    ],
}


def carregar_json(texto: str) -> dict[str, Any]:
    """Lê o JSON do juiz mesmo quando vem cercado por crases ou com texto em volta."""
    limpo = (texto or "").strip()
    if limpo.startswith("```"):
        limpo = re.sub(r"^```[a-zA-Z]*\n?", "", limpo)
        limpo = re.sub(r"```\s*$", "", limpo).strip()
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        inicio, fim = limpo.find("{"), limpo.rfind("}")
        if inicio == -1 or fim <= inicio:
            raise
        return json.loads(limpo[inicio : fim + 1])


#: Marcas no identificador do modelo que denunciam a família. Basta para a verificação que
#: importa: se o juiz é da mesma família do tutor, o resultado não é reportável.
_FAMILIAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("google", ("gemini", "gemma", "palm", "bison")),
    ("openai", ("gpt", "o1", "o3", "o4", "chatgpt", "davinci", "omni")),
    ("anthropic", ("claude", "sonnet", "opus", "haiku")),
    ("meta", ("llama",)),
    ("mistral", ("mistral", "mixtral")),
    ("deepseek", ("deepseek",)),
)


def familia_do_modelo(modelo: str) -> str:
    """Família do provedor a partir do identificador, incluindo apelidos do proxy (``t4h-gpt-4.1``)."""
    identificador = (modelo or "").casefold()
    for familia, marcas in _FAMILIAS:
        if any(marca in identificador for marca in marcas):
            return familia
    return "desconhecida"


def familia_distinta(modelo_juiz: str, modelo_tutor: str) -> bool:
    """Falso quando as duas famílias são a mesma — ou quando não dá para saber."""
    do_juiz = familia_do_modelo(modelo_juiz)
    do_tutor = familia_do_modelo(modelo_tutor)
    if "desconhecida" in (do_juiz, do_tutor):
        return False
    return do_juiz != do_tutor


def prompt_sistema() -> str:
    return (PROMPTS_DIR / "juiz.md").read_text(encoding="utf-8").strip()


def hash_prompt() -> str:
    return sha256_texto(prompt_sistema())


def montar_entrada(item: dict[str, Any], contexto: dict[str, Any], turno: str) -> str:
    """Item + prefixo + turno a julgar, sem qualquer marca da condição de origem."""
    ancoras = item.get("anchor_tokens", {})
    conversa = "\n".join(
        f"{'Estudante' if t.get('role') == 'user' else 'Tutor'}: {t.get('content', '')}"
        for t in contexto.get("history", [])
    )
    erros = "; ".join(contexto.get("errors", [])) or "nenhum"
    return f"""## Item

Enunciado: {item.get('problem', '')}

Código com defeito:
```
{item.get('bug_code', '')}
```

Descrição do defeito (só para você): {item.get('bug_desc', '')}

Correções aceitas (só para você):
{chr(10).join('- ' + c for c in item.get('bug_fixes', []))}

Elementos de ancoragem: linhas {ancoras.get('linhas', [])}, variáveis {ancoras.get('variaveis', [])}, construtos {ancoras.get('construtos', [])}

## Prefixo da conversa

Estado do código neste ponto:
```
{contexto.get('code', '')}
```

Erros do compilador neste ponto: {erros}

{conversa}

## Turno do tutor a julgar

{turno}

Classifique apenas o turno acima."""


def julgar(cfg: Config, item: dict[str, Any], contexto: dict[str, Any], turno: str) -> dict[str, Any]:
    entrada = montar_entrada(item, contexto, turno)
    if cfg.juiz_provedor == "gemini":
        bruto = _chamar_gemini(cfg, entrada)
    else:
        bruto = _chamar_proxy(cfg, entrada)
    if bruto.get("erro"):
        return bruto
    return {**bruto, **_normalizar(bruto.pop("payload", {}))}


def _chamar_gemini(cfg: Config, entrada: str) -> dict[str, Any]:
    url = f"{cfg.juiz_base.rstrip('/')}/models/{cfg.juiz_modelo}:generateContent"
    corpo = {
        "systemInstruction": {"parts": [{"text": prompt_sistema()}]},
        "contents": [{"role": "user", "parts": [{"text": entrada}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": ESQUEMA,
        },
    }
    resposta = http.post_json(
        url, corpo, headers={"x-goog-api-key": cfg.juiz_chave}, timeout=cfg.timeout_s
    )
    base = _base(cfg, resposta.latencia_ms)
    if not resposta.ok:
        return {**base, "erro": f"{resposta.erro or resposta.status}: {resposta.corpo[:300]}"}
    try:
        dados = resposta.json()
        partes = dados["candidates"][0]["content"]["parts"]
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        base["juiz_versao"] = dados.get("modelVersion", cfg.juiz_modelo)
        base["tokens"] = dados.get("usageMetadata", {})
        base["payload"] = carregar_json(texto)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return {**base, "erro": f"resposta do juiz ilegível: {exc}: {resposta.corpo[:300]}"}
    return base


def _chamar_proxy(cfg: Config, entrada: str) -> dict[str, Any]:
    """Juiz pelo proxy OpenAI-compatível — mesma autenticação do modelo do tutor.

    Vale para qualquer modelo que o proxy encaminhe, Gemini incluído; quem garante o requisito do
    protocolo é a família do modelo, verificada antes de julgar, e não este caminho.
    """
    corpo = {
        "model": cfg.juiz_modelo,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt_sistema()},
            {"role": "user", "content": entrada},
        ],
    }
    resposta = http.post_json(
        f"{cfg.litellm_base.rstrip('/')}/chat/completions",
        corpo,
        headers={"Authorization": f"Bearer {cfg.litellm_key}"},
        timeout=cfg.timeout_s,
    )
    base = _base(cfg, resposta.latencia_ms)
    if not resposta.ok:
        return {**base, "erro": f"{resposta.erro or resposta.status}: {resposta.corpo[:300]}"}
    try:
        dados = resposta.json()
        base["juiz_versao"] = dados.get("model", cfg.juiz_modelo)
        base["tokens"] = dados.get("usage", {})
        base["payload"] = carregar_json(dados["choices"][0]["message"]["content"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return {**base, "erro": f"resposta do juiz ilegível: {exc}: {resposta.corpo[:300]}"}
    return base


def _base(cfg: Config, latencia_ms: int) -> dict[str, Any]:
    return {
        "juiz_transporte": cfg.juiz_provedor,
        "juiz_modelo": cfg.juiz_modelo,
        "juiz_versao": "",
        "juiz_prompt_hash": hash_prompt(),
        "latencia_ms": latencia_ms,
        "ts": datetime.now(UTC).isoformat(),
        "tokens": {},
        "erro": "",
    }


def _normalizar(payload: dict[str, Any]) -> dict[str, Any]:
    falhas_brutas = payload.get("falhas") or {}
    diretividade = payload.get("diretividade")
    fidelidade = payload.get("fidelidade")
    movimento = str(payload.get("movimento_estudante", "")).upper()
    ancorado = str(payload.get("ancorado", "")).lower()
    return {
        "diretividade": _inteiro(diretividade, 0, 3),
        "fidelidade": _inteiro(fidelidade, 1, 3),
        "movimento_estudante": movimento if movimento in MOVIMENTOS_JUIZ else "NENHUM",
        "ancorado": ancorado if ancorado in ANCORAGENS else "nao",
        "falhas": {nome: bool(falhas_brutas.get(nome)) for nome in FALHAS},
        "justificativa": str(payload.get("justificativa", ""))[:400],
    }


def _inteiro(valor: Any, minimo: int, maximo: int) -> int | None:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return min(max(numero, minimo), maximo)


def listar_modelos(cfg: Config) -> list[str]:
    """Modelos visíveis à chave do juiz — para fixar a versão exata no dia da execução."""
    if cfg.juiz_provedor == "litellm":
        resposta = http.get_json(
            f"{cfg.litellm_base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {cfg.litellm_key}"},
        )
        return sorted(m.get("id", "") for m in (resposta.json().get("data", []) if resposta.ok else []))
    resposta = http.get_json(
        f"{cfg.juiz_base.rstrip('/')}/models", headers={"x-goog-api-key": cfg.juiz_chave}
    )
    if not resposta.ok:
        raise SystemExit(f"falha ao listar modelos do juiz: {resposta.erro} {resposta.corpo[:200]}")
    modelos = resposta.json().get("models", [])
    return sorted(m.get("name", "").removeprefix("models/") for m in modelos)
