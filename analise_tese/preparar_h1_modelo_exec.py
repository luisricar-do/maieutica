"""Variante de ``preparar_h1_modelo`` com saída separada por execução.

Idêntica em conteúdo a ``analise_tese.preparar_h1_modelo`` — mesmas colunas, mesma filtragem
por ``entra_na_inferencia`` —, mas escreve em ``saida/<AVALIACAO_EXECUCAO>/h1_modelo.csv`` em vez
do caminho de fenda única ``saida/h1_modelo.csv``.

Porquê: ``analise_tese/poder_h1_corpus.R`` lê ``saida/h1_modelo.csv`` **como sendo o ciclo 1** —
é dali que tira a linha de controlo que reproduz o EP 0,617. Correr a preparação sobre `cap5`
pelo caminho antigo sobrescreve esse ficheiro e a linha de controlo passa a comparar o ciclo 2
consigo mesmo, sem erro nenhum a assinalar. É o mesmo padrão que ``CICLOS.md`` regista na seção
«O manifesto grava proxies do estado»: o caminho é um proxy da execução e não a identifica.

    AVALIACAO_EXECUCAO=cap5 python -m analise_tese.preparar_h1_modelo_exec
"""

from __future__ import annotations

import csv

from analise_tese.apurar_h1_h2 import ANALISE, EXECUCAO_ID, SAIDA
from analise_tese.preparar_h1_modelo import COLUNAS


def main() -> None:
    with (ANALISE / "turnos_julgados.csv").open(encoding="utf-8", newline="") as arquivo:
        largo = {ln["chave"]: ln for ln in csv.DictReader(arquivo)}
    with (ANALISE / "h1_turnos.csv").open(encoding="utf-8", newline="") as arquivo:
        h1 = [ln for ln in csv.DictReader(arquivo) if ln["entra_na_inferencia"] == "True"]

    destino_dir = SAIDA / EXECUCAO_ID
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / "h1_modelo.csv"
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        for linha in h1:
            fonte = largo.get(linha["chave"], {})
            escritor.writerow({
                "chave": linha["chave"],
                "item_id": linha["item_id"],
                "prefixo_id": linha["prefixo_id"],
                "dialogo_id": linha["item_id"],
                "condicao": linha["condicao"],
                "execucao": linha["execucao"],
                "k": linha["k"],
                "movimento": linha["movimento_anotado"],
                "estagnacao_acumulada": linha["estagnacao_acumulada"],
                "diretividade": linha["diretividade"],
                "diretividade_anterior": linha["diretividade_anterior"],
                "prioridade": fonte.get("prioridade", ""),
                "origem": linha["origem"],
                "tipo_bug": linha["tipo_bug"],
                "comprimento": fonte.get("comprimento", ""),
                "houve_edicao": fonte.get("houve_edicao", ""),
            })
    print(f"{destino} — {len(h1)} turnos elegíveis (execução {EXECUCAO_ID})")


if __name__ == "__main__":
    main()
