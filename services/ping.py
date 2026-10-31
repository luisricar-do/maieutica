"""Health check simples (liveness), com o commit da imagem."""

import os


def ping_response() -> dict[str, object]:
    # ``BUILD_SHA`` vem do build da imagem na esteira, que espera o ping devolvê-lo para saber
    # que a revisão nova já responde. Fora da imagem (``make start``) fica ``None``.
    return {"pong": True, "build": os.getenv("BUILD_SHA") or None}
