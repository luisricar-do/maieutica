"""Reanotação dos 20 itens novos pela regra de conteúdo do ciclo 1 (opção 1).

Mapa explícito: item -> {índice do turno no diálogo: rótulo novo}. Só toca em `movimento`.
"""
import json
import pathlib
import sys
from collections import Counter

P, E, R = "PROGRESSO", "ESTAGNACAO", "REGRESSAO"

MAPA = {
 "tese_07_soma_multiplos":        {2:P, 4:P, 8:P, 10:R, 12:P},
 "tese_08_troca_valores":         {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_09_posicao_maior":         {2:P, 4:P, 8:R, 10:P, 12:P},
 "tese_10_faixa_valores":         {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_11_soma_ate_zero":         {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_12_menor_valor":           {2:P, 4:P, 8:P, 10:R, 12:P},
 "tese_13_acima_da_media":        {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_14_soma_incompleta":       {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_15_classifica_nota":       {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_16_conta_fora_do_se":      {2:P, 4:P, 8:P, 10:R, 12:P},
 "tese_17_media_dos_pares":       {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_18_busca_mensagem":        {2:R, 4:P, 8:P, 10:P, 12:P},
 "tese_19_soma_do_indice":        {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_20_primeira_ocorrencia":   {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_21_conta_duplicado":       {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_22_media_movel":           {2:E, 4:P, 8:P, 10:P, 12:P},
 "tese_23_incremento_duplo":      {2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_24_menor_aninhado":        {2:P, 4:E, 8:P, 10:P, 12:P},
 "tese_25_contador_nao_reiniciado":{2:P, 4:P, 8:P, 10:P, 12:P},
 "tese_26_soma_quadrados":        {2:P, 4:P, 8:P, 10:P, 12:P},
}

#: Justificação de cada turno que NÃO vira PROGRESSO, e das chamadas discutíveis.
RAZOES = {
 ("tese_07_soma_multiplos",10): "REG: acerta 'uma a cada volta', mas afirma que a linha 'só põe zero, não tira nada' — hipótese incorreta afirmada.",
 ("tese_09_posicao_maior",8):   "REG: 'Vale 1. E o programa imprimiu 1. Então está certo' — dá por correto o que está defeituoso (cf. tese_02 no ciclo 1).",
 ("tese_12_menor_valor",10):    "REG: propõe inverter a comparação, que procuraria o maior (cf. 65_66 no ciclo 1, proposta errada = regressão).",
 ("tese_16_conta_fora_do_se",10):"REG: afirma que 'ele conta quando a condição é verdadeira', que é falso para o código como está.",
 ("tese_18_busca_mensagem",2):  "REG: 'a mensagem não tem nada a ver com o laço' é falso sobre o código escrito (cf. 56_15 no ciclo 1).",
 ("tese_22_media_movel",2):     "EST: 'Não sei' com observação que não avança (cf. 0_0 'Nao sei bem o que mais dizer aqui').",
 ("tese_24_menor_aninhado",4):  "EST: responde à pergunta errada; o tutor corrige 'a minha pergunta é anterior'. Discutível: a afirmação factual que faz é verdadeira.",
 ("tese_17_media_dos_pares",2): "PRO discutível: abre com 'Não sei' mas estabelece 6/2=3, conteúdo novo e correto.",
 ("tese_07_soma_multiplos",4):  "PRO discutível: responde onde os três entram e afirma, corretamente, que a condição está certa — o tutor confirma.",
}

BANCO = pathlib.Path("avaliacao/banco")
linhas = []
for ident, alteracoes in MAPA.items():
    caminho = BANCO / f"{ident}.json"
    bruto = caminho.read_text(encoding="utf-8")
    item = json.loads(bruto)
    for indice, novo in sorted(alteracoes.items()):
        turno = item["dialogo"][indice]
        assert turno["papel"] == "estudante", (ident, indice)
        antigo = turno.get("movimento", "")
        linhas.append((ident, indice, antigo, novo, turno["texto"],
                       RAZOES.get((ident, indice), "")))
        turno["movimento"] = novo
    if "--aplicar" in sys.argv:
        caminho.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

mudados = [linha for linha in linhas if linha[2] != linha[3]]
print(f"turnos no mapa: {len(linhas)}; alterados: {len(mudados)}")
print("de →  para:", Counter((linha[2], linha[3]) for linha in mudados))

destino = pathlib.Path(sys.argv[sys.argv.index("--relatorio")+1]) if "--relatorio" in sys.argv else None
if destino:
    out = ["# Reanotação dos 20 itens novos — regra de conteúdo do ciclo 1", "",
           "| item | turno | de | para | fala do estudante | nota |", "|---|---|---|---|---|---|"]
    for ident, indice, antigo, novo, texto, razao in linhas:
        marca = "**" if antigo != novo else ""
        out.append(f"| {ident} | E[{indice}] | {antigo} | {marca}{novo}{marca} | {texto.replace('|','/')} | {razao} |")
    destino.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"relatório em {destino}")
