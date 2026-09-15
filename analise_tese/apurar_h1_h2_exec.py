"""``apurar_h1_h2`` com a saída separada por execução.

Mesmo cálculo, byte a byte — este módulo não recalcula nada: redireciona ``SAIDA`` para
``saida/<AVALIACAO_EXECUCAO>/`` e chama ``apurar_h1_h2.main()``. Existe pela mesma razão que
``preparar_h1_modelo_exec``: ``saida/apuracao_h1_h2.json`` é caminho de fenda única e correr
duas execuções pelo caminho antigo faz a segunda apagar a primeira sem aviso.

    AVALIACAO_EXECUCAO=cap5 python -m analise_tese.apurar_h1_h2_exec
"""

from __future__ import annotations

from analise_tese import apurar_h1_h2

apurar_h1_h2.SAIDA = apurar_h1_h2.SAIDA / apurar_h1_h2.EXECUCAO_ID

if __name__ == "__main__":
    apurar_h1_h2.main()
