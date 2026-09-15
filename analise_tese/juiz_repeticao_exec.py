"""``juiz_repeticao`` com os ficheiros separados por execução.

Mesmo cálculo; só redirecciona a 2.ª passagem e o seu relatório para
``saida/<AVALIACAO_EXECUCAO>/``, pela mesma razão de ``apurar_h1_h2_exec``: o caminho antigo é de
fenda única, e aqui a fenda é cara — a 2.ª passagem são 210 chamadas ao juiz do protocolo que
não se repetem de graça, e um ``--executar`` sobre a execução errada, pelo caminho antigo,
**retomaria** a passagem do ciclo 1 com turnos do ciclo 2 dentro do mesmo ficheiro.

``cap4`` fica no caminho histórico (``saida/juizos_repeticao.jsonl``), que é onde a sua 2.ª
passagem está versionada; apontá-lo para ``saida/cap4/`` faria o ``--executar`` não a
encontrar e gastar as 210 chamadas outra vez.

    AVALIACAO_EXECUCAO=cap5 python -m analise_tese.juiz_repeticao_exec              # simula
    AVALIACAO_EXECUCAO=cap5 python -m analise_tese.juiz_repeticao_exec --executar   # 210 chamadas
    AVALIACAO_EXECUCAO=cap5 python -m analise_tese.juiz_repeticao_exec --kappa      # → saida/cap5/
"""

from __future__ import annotations

from analise_tese import comum, juiz_repeticao

if comum.EXECUCAO_ID != "cap4":
    _pasta = comum.SAIDA / comum.EXECUCAO_ID
    juiz_repeticao.ARQUIVO_REPETICAO = _pasta / "juizos_repeticao.jsonl"
    juiz_repeticao.ARQUIVO_KAPPA = _pasta / "juiz_repeticao_kappa.json"

if __name__ == "__main__":
    juiz_repeticao.main()
