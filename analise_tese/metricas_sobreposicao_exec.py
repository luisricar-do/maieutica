"""``metricas_sobreposicao`` com a saída separada por execução.

Mesmo cálculo; só redireciona ``SAIDA`` para ``saida/<AVALIACAO_EXECUCAO>/``, pela mesma razão
de ``apurar_h1_h2_exec``.

    AVALIACAO_EXECUCAO=cap5 <venv-metricas>/bin/python -m analise_tese.metricas_sobreposicao_exec
"""

from __future__ import annotations

import os

from analise_tese import metricas_sobreposicao

metricas_sobreposicao.SAIDA = (
    metricas_sobreposicao.SAIDA / os.environ.get("AVALIACAO_EXECUCAO", "cap4"))

if __name__ == "__main__":
    metricas_sobreposicao.main()
