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

**A chave falha alto, e o valor em vigor vai nos dados.** Um valor que não seja um dos dois
literais para o serviço no arranque (``verificar_configuracao``, chamada no carregamento do
``function_app``) em vez de cair em ``regra`` sem dizer nada. A queda silenciosa é o defeito a
evitar: a dissertação declara ``regra`` em §4.3, e um ``modeo`` escrito à pressa numa App Setting
produziria uma coleta que contradiz o texto sem deixar rasto. Pelo mesmo motivo o valor efetivo
é gravado no ``tutorMeta`` de cada turno, no registro estruturado e no envelope de cada lote de
telemetria: depois da aula não há como reconstituí-lo do ambiente.
"""

import os

EVALUATION_MODE_ENV = "EVALUATION_MODE"
CLASSIFICADOR_ENV = "CLASSIFICADOR_DE_MOVIMENTO"

#: Os únicos valores aceites por ``CLASSIFICADOR_DE_MOVIMENTO``. O primeiro é o padrão.
CLASSIFICADORES = ("regra", "modelo")

_TRUTHY = frozenset({"1", "true", "yes", "on", "sim"})


class ConfiguracaoInvalida(RuntimeError):
    """Variável de ambiente com valor fora do domínio declarado."""


def evaluation_mode() -> bool:
    """``True`` quando o serviço corre na configuração congelada da avaliação."""
    return (os.getenv(EVALUATION_MODE_ENV) or "").strip().casefold() in _TRUTHY


def classificador_de_movimento() -> str:
    """O classificador em vigor: ``regra`` ou ``modelo``.

    Ausente ou vazia, a chave vale ``regra``. Qualquer outro valor levanta
    ``ConfiguracaoInvalida`` — não há terceiro comportamento a que cair.
    """
    bruto = (os.getenv(CLASSIFICADOR_ENV) or "").strip()
    if not bruto:
        return CLASSIFICADORES[0]
    valor = bruto.casefold()
    if valor not in CLASSIFICADORES:
        raise ConfiguracaoInvalida(
            f"{CLASSIFICADOR_ENV}={bruto!r} não é um valor válido; "
            f"use um de {', '.join(CLASSIFICADORES)}."
        )
    return valor


def classificador_por_modelo() -> bool:
    """``True`` quando o nó de classificação substitui a regra textual determinística."""
    return classificador_de_movimento() == "modelo"


def verificar_configuracao() -> None:
    """Lê as chaves de política no arranque, para que um valor inválido falhe já.

    Chamada no carregamento do ``function_app``: se a App Setting estiver errada, o *worker*
    não sobe, em vez de servir uma sessão inteira com a política que ninguém escolheu.
    """
    classificador_de_movimento()
