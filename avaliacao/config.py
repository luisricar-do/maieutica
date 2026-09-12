"""Configuração da bancada: endereços, credenciais, caminhos e hashes de reprodutibilidade.

As variáveis são lidas do ambiente e, como conveniência de desenvolvimento, do
``local.settings.json`` da raiz (secção ``Values``) — o mesmo arquivo que o Azure Functions usa,
para não duplicar credenciais. O ambiente sempre prevalece sobre o arquivo.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BANCO_DIR = RAIZ / "banco"
TRADUCAO_DIR = RAIZ / "traducao"
PROMPTS_DIR = RAIZ / "prompts"
EXECUCOES_DIR = RAIZ / "execucoes"

#: Modelo do juiz na corrida **reportável**: família distinta da do tutor (Zheng et al., 2023),
#: que é o que o protocolo exige. O transporte é indiferente — um Gemini servido pelo mesmo proxy
#: LiteLLM satisfaz o desenho tanto quanto a API direta da Google. Caro: só sob pedido explícito
#: (``--juiz-protocolo`` ou ``JUIZ_MODELO``). A versão exata é fixada no dia da execução e
#: registrada no manifesto a partir do que a API devolve.
JUIZ_MODELO_PROTOCOLO = "gemini-3.1-pro-preview"

#: Modelo do juiz por omissão: barato, para desenvolver o harness e ensaiar o encanamento. É da
#: mesma família do tutor, portanto **não** sustenta resultado reportável — o comando avisa e o
#: manifesto grava ``juiz_familia_distinta: false``.
JUIZ_MODELO_PADRAO = "gpt-4o"

#: Transporte do juiz: pelo proxy (mesma autenticação do modelo do tutor) ou pela API da Google.
TRANSPORTES_JUIZ = ("litellm", "gemini")
JUIZ_BASE_GEMINI = "https://generativelanguage.googleapis.com/v1beta"

#: Número de execuções por prefixo por condição (sobe para 5 se a variância do piloto for alta).
EXECUCOES_PADRAO = 3
#: Reexecuções antes de marcar ``falha_tecnica``.
REEXECUCOES_PADRAO = 2


def carregar_settings_local(caminho: Path | None = None) -> None:
    """Preenche o ambiente com ``local.settings.json`` sem sobrescrever o que já existe."""
    alvo = caminho or (RAIZ.parent / "local.settings.json")
    if not alvo.is_file():
        return
    try:
        valores = json.loads(alvo.read_text(encoding="utf-8")).get("Values", {})
    except (json.JSONDecodeError, OSError):
        return
    for chave, valor in valores.items():
        if isinstance(valor, str) and valor and not os.getenv(chave):
            os.environ[chave] = valor


def _env(nome: str, padrao: str = "") -> str:
    return (os.getenv(nome) or padrao).strip()


@dataclass(frozen=True)
class Config:
    """Parâmetros de uma execução da bancada."""

    api_base: str = field(default_factory=lambda: _env("AVALIACAO_API_BASE", "http://localhost:7071/api"))
    litellm_base: str = field(default_factory=lambda: _env("LITELLM_BASE_URL"))
    litellm_key: str = field(default_factory=lambda: _env("LITELLM_API_KEY") or _env("OPENAI_API_KEY"))
    modelo_base: str = field(default_factory=lambda: _env("LITELLM_MODEL", "gpt-4o-mini"))
    juiz_provedor: str = field(default_factory=lambda: _env("JUIZ_PROVEDOR", "litellm"))
    juiz_modelo: str = field(default_factory=lambda: _env("JUIZ_MODELO", JUIZ_MODELO_PADRAO))
    juiz_chave: str = field(default_factory=lambda: _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"))
    juiz_base: str = field(default_factory=lambda: _env("JUIZ_BASE_URL", JUIZ_BASE_GEMINI))
    timeout_s: float = field(default_factory=lambda: float(_env("AVALIACAO_TIMEOUT", "120")))
    paralelismo: int = field(default_factory=lambda: int(_env("AVALIACAO_PARALELISMO", "4")))

    def __post_init__(self) -> None:
        # "openai" é como o transporte pelo proxy se chamava antes; mantém-se como apelido.
        transporte = (self.juiz_provedor or "litellm").strip().casefold()
        object.__setattr__(self, "juiz_provedor", "litellm" if transporte == "openai" else transporte)

    def exige_artefato(self) -> None:
        if not self.api_base:
            raise SystemExit("AVALIACAO_API_BASE vazio: suba o serviço com `make start` e aponte a base.")

    def exige_juiz(self) -> None:
        if self.juiz_provedor not in TRANSPORTES_JUIZ:
            raise SystemExit(f"JUIZ_PROVEDOR inválido: use {' ou '.join(TRANSPORTES_JUIZ)}.")
        if self.juiz_provedor == "gemini" and not self.juiz_chave:
            raise SystemExit(
                "GEMINI_API_KEY vazio. Use JUIZ_PROVEDOR=litellm para acionar o juiz pelo mesmo "
                "proxy (e mesma autenticação) do modelo do tutor."
            )
        if self.juiz_provedor == "litellm" and not self.litellm_base:
            raise SystemExit("JUIZ_PROVEDOR=litellm exige LITELLM_BASE_URL e LITELLM_API_KEY.")


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def commit_atual(repo: Path) -> str:
    """SHA do HEAD do repositório, para o congelamento (Subseção 4.6 da dissertação)."""
    try:
        saida = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return saida.stdout.strip() if saida.returncode == 0 else ""
