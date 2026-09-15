"""
Configuração de execução do artefato.

``EVALUATION_MODE`` congela o artefato na configuração que a dissertação avalia: sem
recuperação de documentação (RAG) em nenhuma intenção e sem a ferramenta
``suggest_documentation``, de modo que "RAG desligado em toda a avaliação" valha literalmente,
tanto em bancada como em uso real. Fora desse modo, o comportamento é o de produção.

``CLASSIFICADOR_DE_MOVIMENTO`` escolhe quem classifica o movimento do estudante no degrau em que
o texto decide, e portanto que valor de estagnação acumulada a política consome. O padrão é
``regra`` — o classificador determinístico de ``agents.movement``, que é o artefato
pré-registado. ``modelo`` liga o nó ``agents.classifier``. Existir como chave, e não como edição
de código, é o que torna a corrida A/A — a mesma bancada com os dois estimadores — uma questão
de configuração.
"""

import os

EVALUATION_MODE_ENV = "EVALUATION_MODE"
CLASSIFICADOR_ENV = "CLASSIFICADOR_DE_MOVIMENTO"

_TRUTHY = frozenset({"1", "true", "yes", "on", "sim"})


def evaluation_mode() -> bool:
    """``True`` quando o serviço corre na configuração congelada da avaliação."""
    return (os.getenv(EVALUATION_MODE_ENV) or "").strip().casefold() in _TRUTHY


def classificador_por_modelo() -> bool:
    """``True`` quando o nó de classificação substitui a regra textual determinística."""
    return (os.getenv(CLASSIFICADOR_ENV) or "regra").strip().casefold() == "modelo"
