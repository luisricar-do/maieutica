"""
Configuração de execução do artefato.

``EVALUATION_MODE`` congela o artefato na configuração que a dissertação avalia: sem
recuperação de documentação (RAG) em nenhuma intenção e sem a ferramenta
``suggest_documentation``, de modo que "RAG desligado em toda a avaliação" valha literalmente,
tanto em bancada como em uso real. Fora desse modo, o comportamento é o de produção.
"""

import os

EVALUATION_MODE_ENV = "EVALUATION_MODE"

_TRUTHY = frozenset({"1", "true", "yes", "on", "sim"})


def evaluation_mode() -> bool:
    """``True`` quando o serviço corre na configuração congelada da avaliação."""
    return (os.getenv(EVALUATION_MODE_ENV) or "").strip().casefold() in _TRUTHY
