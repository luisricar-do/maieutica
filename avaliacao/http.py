"""Cliente HTTP mínimo da bancada: JSON por ``urllib``, sem dependências novas.

A bancada é deliberadamente leve — só chamadas de API. Cada chamada devolve estado, corpo e
latência, e quem chama decide o que é falha técnica (Subseção 4.3.3 da dissertação).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Resposta:
    status: int
    corpo: str
    latencia_ms: int
    erro: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.erro

    def json(self) -> Any:
        return json.loads(self.corpo)


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> Resposta:
    corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    pedido = urllib.request.Request(url, data=corpo, method="POST")
    pedido.add_header("Content-Type", "application/json; charset=utf-8")
    for chave, valor in (headers or {}).items():
        pedido.add_header(chave, valor)
    return _executar(pedido, timeout)


def get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 60.0) -> Resposta:
    pedido = urllib.request.Request(url, method="GET")
    for chave, valor in (headers or {}).items():
        pedido.add_header(chave, valor)
    return _executar(pedido, timeout)


def _executar(pedido: urllib.request.Request, timeout: float) -> Resposta:
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            texto = resposta.read().decode("utf-8", errors="replace")
            return Resposta(resposta.status, texto, _ms(inicio))
    except urllib.error.HTTPError as exc:  # 4xx/5xx com corpo
        texto = exc.read().decode("utf-8", errors="replace")
        return Resposta(exc.code, texto, _ms(inicio), erro=f"HTTP {exc.code}")
    except Exception as exc:  # timeout, DNS, conexão recusada
        return Resposta(0, "", _ms(inicio), erro=f"{type(exc).__name__}: {exc}")


def _ms(inicio: float) -> int:
    return int((time.perf_counter() - inicio) * 1000)
