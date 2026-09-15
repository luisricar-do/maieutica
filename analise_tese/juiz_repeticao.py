"""Tarefa H.1 — estabilidade de repetição do juiz sobre a subamostra de validação.

O protocolo pede que a subamostra seja julgada **duas vezes**, em chamadas independentes, e que
se reporte a concordância do juiz consigo mesmo no mesmo limiar de 0,60. Um juiz que não se
reproduz não sustenta a classificação, ainda que o κ contra o humano passe.

Este script re-julga os **mesmos 210 turnos** de ``validacao_humana/mapa_amostra.json`` da
execução escolhida (``AVALIACAO_EXECUCAO``, padrão ``cap4``) com o prompt e o modelo congelados
no seu manifesto (``prompts/juiz.md``, hash ``5dc2baa3…``; ``gemini-3.1-pro-preview``), e
escreve num **ficheiro novo**:

    analise_tese/saida/juizos_repeticao.jsonl                 # cap4, o caminho histórico
    analise_tese/saida/<execução>/juizos_repeticao.jsonl      # via ``juiz_repeticao_exec``

Nada em ``avaliacao/execucoes/<execução>/`` é lido senão para montar a entrada, e nada é
reescrito. Os vereditos originais ficam intactos.

Três modos:

    python -m analise_tese.juiz_repeticao                # simula: chamadas e tokens, não chama nada
    python -m analise_tese.juiz_repeticao --executar     # faz as 210 chamadas
    python -m analise_tese.juiz_repeticao --kappa        # κ 1.ª × 2.ª passagem, por variável, com IC

``--executar`` recusa-se a correr se o hash do prompt em disco não for o da corrida, se o
modelo configurado não for o do manifesto, ou se o proxy não encaminhar esse modelo
(``/v1/models``): repetir com outro prompt ou outro modelo não mede estabilidade, mede outra
coisa. Cada veredito grava ``modelo_conferido``: o identificador que a API devolveu é o pedido
**e** está na lista do proxy. O relatório do ``--kappa`` conta-os, N/N.

O IC de cada κ é percentílico por bootstrap sobre os pares (``estatistica.intervalo_bootstrap``,
2 000 reamostras, semente fixa). Não depende da codificação humana: a estabilidade do juiz
mede-se antes de a primeira rodada existir, e é por isso que ``kappa.json`` é opcional aqui.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from avaliacao import juiz  # noqa: E402
from avaliacao.config import BANCO_DIR, Config, carregar_settings_local  # noqa: E402
from avaliacao.estatistica import intervalo_bootstrap, kappa_cohen, kappa_ponderado  # noqa: E402
from avaliacao.itens import carregar_banco, turnos_de_referencia  # noqa: E402
from avaliacao.julgamento import indexar_prefixos  # noqa: E402
from analise_tese import comum  # noqa: E402

#: Caminhos da 2.ª passagem. ``juiz_repeticao_exec`` redirecciona-os para ``saida/<execução>/``;
#: aqui ficam os históricos de ``cap4``, que é onde a 2.ª passagem do ciclo 1 está versionada.
ARQUIVO_REPETICAO = comum.SAIDA / "juizos_repeticao.jsonl"
ARQUIVO_KAPPA = comum.SAIDA / "juiz_repeticao_kappa.json"
ESCALAS = {"diretividade": (0, 1, 2, 3), "fidelidade": (1, 2, 3)}
ACEITACAO_KAPPA = 0.60
REAMOSTRAS = 2000


def _pendencias(dados: dict) -> list[dict]:
    """Uma entrada de julgamento por turno da amostra, gerado ou de referência."""
    itens = carregar_banco(BANCO_DIR)
    prefixos = indexar_prefixos(itens)
    referencias = {r["id"]: r for item in itens for r in turnos_de_referencia(item)}

    pendencias = []
    for id_cego in sorted(dados["mapa"]):
        chave = dados["mapa"][id_cego]
        turno = dados["turnos"].get(chave)
        if turno is not None:
            prefixo = prefixos[turno["prefixo_id"]]
            pendencias.append(
                {
                    "id_cego": id_cego,
                    "chave": chave,
                    "unidade": "gerado",
                    "item_id": turno["item_id"],
                    "turno": str(turno.get("message", "")).strip(),
                    "contexto": {
                        "history": prefixo.history,
                        "code": prefixo.code,
                        "errors": prefixo.errors,
                    },
                }
            )
            continue
        referencia = referencias[chave]
        pendencias.append(
            {
                "id_cego": id_cego,
                "chave": chave,
                "unidade": "referencia",
                "item_id": referencia["item_id"],
                "turno": referencia["texto"],
                "contexto": {
                    "history": referencia["history"],
                    "code": referencia["code"],
                    "errors": referencia["errors"],
                },
            }
        )
    assert len(pendencias) == len(dados["mapa"])
    return pendencias


def simular(dados: dict) -> dict:
    """Chamadas e tokens da repetição, medidos no consumo real da 1.ª passagem."""
    pendencias = _pendencias(dados)
    chaves = [p["chave"] for p in pendencias]
    entrada = sum(dados["juizos"][c]["tokens"]["prompt_tokens"] for c in chaves)
    saida = sum(dados["juizos"][c]["tokens"]["completion_tokens"] for c in chaves)
    latencias = sorted(dados["juizos"][c]["latencia_ms"] for c in chaves)
    return {
        "execucao": comum.EXECUCAO_ID,
        "chamadas": len(pendencias),
        "gerados": sum(1 for p in pendencias if p["unidade"] == "gerado"),
        "referencia": sum(1 for p in pendencias if p["unidade"] == "referencia"),
        "modelo": dados["manifesto"]["juiz_modelo"],
        "prompt_hash_exigido": dados["manifesto"]["hash_prompt_juiz"],
        "prompt_hash_em_disco": juiz.hash_prompt(),
        "tokens_primeira_passagem": {"entrada": entrada, "saida": saida, "total": entrada + saida},
        "tokens_por_chamada": {
            "entrada_media": round(entrada / len(pendencias), 1),
            "saida_media": round(saida / len(pendencias), 1),
        },
        "latencia_ms": {"mediana": latencias[len(latencias) // 2], "maxima": latencias[-1]},
        "custo_em_dinheiro": (
            "NÃO EXISTE no repositório: não há tabela de preços do proxy LiteLLM aqui. "
            "Multiplique os tokens acima pela tarifa de gemini-3.1-pro-preview na sua conta."
        ),
        "destino": str(ARQUIVO_REPETICAO),
    }


def _modelos_no_proxy(cfg: Config) -> list[str] | None:
    """Lista de ``/v1/models`` da chave do juiz; ``None`` quando o transporte não é o proxy."""
    if cfg.juiz_provedor != "litellm":
        return None
    return juiz.listar_modelos(cfg)


def executar(dados: dict, cfg: Config, paralelismo: int, limite: int | None = None) -> dict:
    esperado = dados["manifesto"]["hash_prompt_juiz"]
    if juiz.hash_prompt() != esperado:
        raise SystemExit(
            f"prompt do juiz em disco ({juiz.hash_prompt()}) não é o da corrida ({esperado}): "
            "a repetição mediria outra coisa."
        )
    if cfg.juiz_modelo != dados["manifesto"]["juiz_modelo"]:
        raise SystemExit(
            f"JUIZ_MODELO={cfg.juiz_modelo!r} difere do manifesto "
            f"({dados['manifesto']['juiz_modelo']!r}); exporte o mesmo modelo."
        )
    cfg.exige_juiz()
    # A conferência que `julgar` faz antes da corrida: o proxy tem de encaminhar o modelo pedido.
    # Sem ela um proxy que recaia noutro modelo produziria uma «segunda passagem» de outro juiz.
    disponiveis = _modelos_no_proxy(cfg)
    if disponiveis is not None and cfg.juiz_modelo not in disponiveis:
        raise SystemExit(
            f"o proxy não encaminha {cfg.juiz_modelo!r} para esta chave; "
            f"disponíveis: {', '.join(disponiveis) or '(nenhum)'}"
        )

    itens = {item["id"]: item for item in carregar_banco(BANCO_DIR)}
    pendencias = _pendencias(dados)
    # Retomável como `julgar`: juízo com erro **não** conta como feito, senão a segunda
    # passagem fica com buracos que uma reexecução nunca preenche.
    feitos = set()
    if ARQUIVO_REPETICAO.is_file():
        feitos = {
            registro["chave"]
            for registro in comum.ndjson(ARQUIVO_REPETICAO)
            if not registro.get("erro") and registro.get("diretividade") is not None
        }
    pendencias = [p for p in pendencias if p["chave"] not in feitos]
    if limite is not None:
        pendencias = pendencias[:limite]

    ARQUIVO_REPETICAO.parent.mkdir(parents=True, exist_ok=True)
    resumo: dict = {
        "execucao": comum.EXECUCAO_ID,
        "destino": str(ARQUIVO_REPETICAO),
        "modelo": cfg.juiz_modelo,
        "modelos_no_proxy": None if disponiveis is None else len(disponiveis),
        "reaproveitados": len(feitos),
        "planejados": len(pendencias),
        "ok": 0,
        "erros": 0,
        "modelo_conferido": 0,
        "tokens": {"entrada": 0, "saida": 0},
    }

    def trabalho(pendencia: dict) -> dict:
        veredito = juiz.julgar(cfg, itens[pendencia["item_id"]], pendencia["contexto"], pendencia["turno"])
        devolvido = str(veredito.get("juiz_versao") or "")
        # O identificador que a API devolveu é o pedido e está na lista do proxy — por chamada,
        # não só antes da corrida. `juiz_versao` recai na configuração se a resposta não trouxer
        # `model` (juiz.py), e é esse risco residual que a lista do proxy fecha.
        veredito["modelo_conferido"] = bool(
            not veredito.get("erro")
            and devolvido == cfg.juiz_modelo
            and (disponiveis is None or devolvido in disponiveis)
        )
        return {
            "chave": pendencia["chave"],
            "id_cego": pendencia["id_cego"],
            "unidade": pendencia["unidade"],
            "item_id": pendencia["item_id"],
            "passagem": 2,
            **veredito,
        }

    with ARQUIVO_REPETICAO.open("a", encoding="utf-8") as arquivo:
        with ThreadPoolExecutor(max_workers=max(1, paralelismo)) as piscina:
            for registro in piscina.map(trabalho, pendencias):
                arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
                arquivo.flush()
                resumo["erros" if registro.get("erro") else "ok"] += 1
                resumo["modelo_conferido"] += int(bool(registro.get("modelo_conferido")))
                uso = registro.get("tokens") or {}
                resumo["tokens"]["entrada"] += int(uso.get("prompt_tokens") or 0)
                resumo["tokens"]["saida"] += int(uso.get("completion_tokens") or 0)
    return resumo


def _funcao(variavel: str):
    if variavel in ESCALAS:
        return lambda x, y: kappa_ponderado(x, y, escala=ESCALAS[variavel])
    return kappa_cohen


def _arredondar(valor: float) -> float | None:
    return None if valor != valor else round(valor, 4)


def _segunda_passagem() -> tuple[list[dict], dict[str, dict]]:
    """Todos os registos da 2.ª passagem, e os bem-sucedidos indexados por chave."""
    if not ARQUIVO_REPETICAO.is_file():
        raise SystemExit(
            f"{ARQUIVO_REPETICAO} não existe: corra `--executar` primeiro. "
            "Sem segunda passagem não há estabilidade a medir."
        )
    todos = comum.ndjson(ARQUIVO_REPETICAO)
    ok = {
        registro["chave"]: registro
        for registro in todos
        if not registro.get("erro") and registro.get("diretividade") is not None
    }
    return todos, ok


def _proveniencia(todos: list[dict], ok: dict[str, dict], manifesto: dict) -> dict:
    """O que o Cap. 4 e o `hashes-congelados.md` citam da 2.ª passagem: modelo, tokens, janela."""
    marcas = sorted(r["ts"] for r in ok.values() if r.get("ts"))
    conferidos = [r.get("modelo_conferido") for r in ok.values()]
    if all(c is None for c in conferidos):
        conferencia = "não registado por chamada (passagem anterior ao campo `modelo_conferido`)"
    else:
        conferencia = f"{sum(1 for c in conferidos if c)}/{len(conferidos)}"
    return {
        "ficheiro": str(ARQUIVO_REPETICAO),
        "registros": len(todos),
        "ok": len(ok),
        "erros": sum(1 for r in todos if r.get("erro")),
        "modelo_pedido": manifesto.get("juiz_modelo"),
        "modelo_devolvido": dict(collections.Counter(r.get("juiz_versao") for r in ok.values())),
        "modelo_conferido_em_v1_models": conferencia,
        "hash_prompt": dict(collections.Counter(r.get("juiz_prompt_hash") for r in ok.values())),
        "hash_prompt_da_corrida": manifesto.get("hash_prompt_juiz"),
        "janela_utc": {"inicio": marcas[0] if marcas else None, "fim": marcas[-1] if marcas else None},
        "tokens": {
            "entrada": sum(int((r.get("tokens") or {}).get("prompt_tokens") or 0) for r in ok.values()),
            "saida": sum(int((r.get("tokens") or {}).get("completion_tokens") or 0) for r in ok.values()),
        },
        "unidades": dict(collections.Counter(r.get("unidade") for r in ok.values())),
    }


def kappa(dados: dict) -> dict:
    todos, segunda = _segunda_passagem()
    saida: dict = {
        "execucao": comum.EXECUCAO_ID,
        "segunda_passagem": _proveniencia(todos, segunda, dados["manifesto"]),
        "ic": f"percentílico, bootstrap sobre os pares, {REAMOSTRAS} reamostras, semente fixa",
        "n_pares": 0,
        "por_variavel": {},
    }
    for variavel in comum.VARIAVEIS:
        a, b = [], []
        for chave, registro in sorted(segunda.items()):
            primeiro = dados["juizos"].get(chave)
            if not primeiro:
                continue
            a.append(comum.valor_juiz(primeiro, variavel))
            b.append(comum.valor_juiz(registro, variavel))
        saida["n_pares"] = len(a)
        if not a:
            continue
        funcao = _funcao(variavel)
        valor = funcao(a, b)
        intervalo = intervalo_bootstrap(a, b, funcao, reamostras=REAMOSTRAS)
        acordos = sum(1 for x, y in zip(a, b) if x == y)
        saida["por_variavel"][variavel] = {
            "kappa": _arredondar(valor),
            "ic95": [_arredondar(intervalo.inferior), _arredondar(intervalo.superior)],
            "reamostras_validas": intervalo.reamostras_validas,
            "bruta": round(acordos / len(a), 3),
            "conta": f"{acordos}/{len(a)}",
        }
    # Sensibilidade: os κ humano×juiz reportados no Cap. 5 recalculados contra a 2.ª passagem.
    # Se a classificação se sustenta, trocar uma passagem pela outra não os move de forma
    # relevante; um κ que só existe numa das passagens não é resultado, é sorteio. Só existe
    # depois da primeira rodada humana; antes dela a secção fica vazia, e diz porquê.
    inverso = {chave: id_cego for id_cego, chave in dados["mapa"].items()}
    saida["sensibilidade_humano_juiz"] = {}
    for variavel in comum.VARIAVEIS:
        humano, primeira, repetida = [], [], []
        for chave, registro in sorted(segunda.items()):
            linha = dados["codificacao"].get(inverso.get(chave, ""))
            valor = comum.valor_humano(linha, variavel) if linha else None
            if valor is None or chave not in dados["juizos"]:
                continue
            humano.append(valor)
            primeira.append(comum.valor_juiz(dados["juizos"][chave], variavel))
            repetida.append(comum.valor_juiz(registro, variavel))
        if not humano:
            continue
        funcao = _funcao(variavel)
        saida["sensibilidade_humano_juiz"][variavel] = {
            "n": len(humano),
            "kappa_1a_passagem": _arredondar(funcao(humano, primeira)),
            "kappa_2a_passagem": _arredondar(funcao(humano, repetida)),
        }
    if not saida["sensibilidade_humano_juiz"]:
        saida["sensibilidade_humano_juiz"] = (
            "sem codificação humana preenchida: a sensibilidade humano×juiz espera pela 1.ª rodada"
        )

    saida["abaixo_da_aceitacao"] = sorted(
        nome
        for nome, v in saida["por_variavel"].items()
        if v["kappa"] is not None and v["kappa"] < ACEITACAO_KAPPA
    )
    saida["indefinidos"] = sorted(
        nome for nome, v in saida["por_variavel"].items() if v["kappa"] is None
    )
    return saida


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--executar", action="store_true", help="faz as chamadas ao juiz")
    analisador.add_argument("--kappa", action="store_true", help="κ 1.ª × 2.ª passagem")
    analisador.add_argument("--paralelismo", type=int, default=4)
    analisador.add_argument("--limite", type=int, default=None, help="teste de fumo: só N chamadas")
    args = analisador.parse_args()

    dados = comum.carregar()
    if args.kappa:
        relatorio = {"H1_estabilidade_do_juiz": kappa(dados)}
        ARQUIVO_KAPPA.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_KAPPA.write_text(
            json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    elif args.executar:
        carregar_settings_local()
        relatorio = {"execucao": executar(dados, Config(), args.paralelismo, args.limite)}
    else:
        relatorio = {"simulacao": simular(dados)}
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
