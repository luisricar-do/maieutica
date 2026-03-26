"""Health check simples (liveness)."""


def ping_response() -> dict[str, object]:
    return {"pong": True}
