"""Prepara o CSV que o modelo ordinal misto de H1 consome (`analise_tese/h1_ordinal.R`).

Junta `h1_turnos.csv` com as colunas que só existem em `turnos_julgados.csv` — prioridade,
comprimento e edição de código — e deixa uma linha por turno elegível. Só leitura.

    python -m analise_tese.preparar_h1_modelo   # → saida/h1_modelo.csv
"""

from __future__ import annotations

import csv

from analise_tese.apurar_h1_h2 import ANALISE, SAIDA

COLUNAS = ("chave", "item_id", "prefixo_id", "dialogo_id", "condicao", "execucao", "k",
           "movimento", "estagnacao_acumulada", "diretividade", "diretividade_anterior",
           "prioridade", "origem", "tipo_bug", "comprimento", "houve_edicao")


def main() -> None:
    with (ANALISE / "turnos_julgados.csv").open(encoding="utf-8", newline="") as arquivo:
        largo = {ln["chave"]: ln for ln in csv.DictReader(arquivo)}
    with (ANALISE / "h1_turnos.csv").open(encoding="utf-8", newline="") as arquivo:
        h1 = [ln for ln in csv.DictReader(arquivo) if ln["entra_na_inferencia"] == "True"]

    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / "h1_modelo.csv"
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        for linha in h1:
            fonte = largo.get(linha["chave"], {})
            escritor.writerow({
                "chave": linha["chave"],
                "item_id": linha["item_id"],
                "prefixo_id": linha["prefixo_id"],
                # Em bancada há um diálogo de referência por item: o fator «diálogo» do plano
                # analítico coincide com o item e não é identificável em separado. Fica aqui
                # explícito para o R poder demonstrá-lo em vez de o esconder.
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
    print(f"{destino} — {len(h1)} turnos elegíveis")


if __name__ == "__main__":
    main()
