"""Linha de comando da bancada.

Etapas, na ordem em que se usam:

    python -m avaliacao importar         # rascunhos a partir do conjunto de Al-Hossami
    python -m avaliacao estados          # erros do compilador e casos de teste, uma vez
    python -m avaliacao validar          # banco de itens e padrões de correção
    python -m avaliacao prefixos         # o que será enviado, sem chamar nada
    python -m avaliacao rodar            # condições A e C sobre todos os prefixos
    python -m avaliacao julgar           # juiz sobre turnos gerados e de referência
    python -m avaliacao analisar         # H1, H2, descritivas, tabelas do Capítulo 5
    python -m avaliacao amostra-humana   # planilhas cegas: rodada completa e terço diferido
    python -m avaliacao kappa            # concordância, depois de preenchidas as planilhas
    python -m avaliacao congelar         # manifesto de reprodutibilidade
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from avaliacao import analise, condicoes, exportacao, importacao, juiz, validacao_humana
from avaliacao.config import (
    BANCO_DIR,
    TRADUCAO_DIR,
    EXECUCOES_PADRAO,
    JUIZ_MODELO_PROTOCOLO,
    REEXECUCOES_PADRAO,
    Config,
    carregar_settings_local,
    commit_atual,
)
from avaliacao.executor import ARQUIVO_TURNOS, executar, montar_tarefas
from avaliacao.itens import avisos_item, carregar_banco, expandir_prefixos, validar_item
from avaliacao.julgamento import ARQUIVO_JUIZOS, julgar_execucao
from avaliacao.registro import (
    atualizar_manifesto,
    diretorio_execucao,
    ler_json,
    ler_ndjson,
    novo_id_execucao,
)


def main(argv: list[str] | None = None) -> int:
    carregar_settings_local()
    args = _parser().parse_args(argv)
    cfg = _config(args)
    itens = _itens(args)
    return args.funcao(args, cfg, itens)


# --------------------------------------------------------------------------- comandos


def _cmd_importar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    fonte = Path(args.fonte).expanduser().resolve()
    if not fonte.is_dir():
        raise SystemExit(f"conjunto original não encontrado em {fonte} (use --fonte)")
    alvos = sorted(fonte.glob(f"{args.dialogo}*.txt")) if args.dialogo else sorted(fonte.glob("*.txt"))
    if not alvos:
        raise SystemExit(f"nenhum diálogo casa com {args.dialogo!r} em {fonte}")

    commit = importacao.commit_do_conjunto(fonte)
    destino = Path(args.saida)
    print(f"conjunto: {fonte}\ncommit:   {commit or '(fora de git)'}\n")
    for caminho in alvos:
        item = importacao.importar(caminho, commit=commit)
        arquivo = importacao.escrever(item, destino)
        faltas = importacao.pendencias(item)
        turnos_tutor = sum(1 for t in item["dialogo"] if t["papel"] == "tutor")
        print(
            f"  {item['id']:<34} prio={item['prioridade']}  "
            f"{turnos_tutor} turnos do tutor, {len(item['estados_codigo'])} estados  -> {arquivo.name}"
        )
        for falta in faltas:
            print(f"      pendente: {falta}")
    print(f"\n{len(alvos)} rascunho(s) em {destino}. Traduza e mova para {args.banco}.")
    return 0


def _cmd_validar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    problemas = [erro for item in itens for erro in validar_item(item)]
    prefixos = [p for item in itens for p in expandir_prefixos(item)]
    print(f"itens: {len(itens)}  |  arquivos em {args.banco}")
    for item in itens:
        do_item = expandir_prefixos(item)
        print(
            f"  {item['id']:<28} origem={item['origem']:<14} bug={item['tipo_bug']:<12} "
            f"prefixos: {sum(1 for p in do_item if p.tipo == 'ouro')} ouro + "
            f"{sum(1 for p in do_item if p.tipo == 'pressao')} pressão"
        )
    print(
        f"\nprefixos: {sum(1 for p in prefixos if p.tipo == 'ouro')} de referência, "
        f"{sum(1 for p in prefixos if p.tipo == 'pressao')} de pressão"
    )
    avisos = [aviso for item in itens for aviso in avisos_item(item)]
    if avisos:
        print(f"\n{len(avisos)} aviso(s) — não invalidam o banco, mas o revisor tem de ver:")
        for aviso in avisos:
            print(f"  - {aviso}")
    if problemas:
        print(f"\n{len(problemas)} problema(s):")
        for problema in problemas:
            print(f"  - {problema}")
        return 1
    print("\nbanco válido.")
    return 0


def _cmd_estados(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    from avaliacao import estados

    runner = estados.caminho_runner(args.runner)
    print(f"motor headless: {runner}")
    escolhidos = {item["id"] for item in itens} if getattr(args, "itens", "") else None
    resumo = estados.precomputar_banco(Path(args.banco), runner, ids=escolhidos)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


def _cmd_prefixos(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    prefixos = [p for item in itens for p in expandir_prefixos(item)]
    if args.json:
        print(json.dumps([p.para_dict() for p in prefixos], ensure_ascii=False, indent=2))
        return 0
    for prefixo in prefixos:
        print(
            f"{prefixo.id:<46} k={prefixo.k} tipo={prefixo.tipo:<8} "
            f"mov={prefixo.movimento_anterior:<17} estag={prefixo.estagnacao_acumulada} "
            f"turnos={len(prefixo.history)}"
        )
    if args.payload and prefixos:
        print("\npayload de exemplo (condição A):")
        print(json.dumps(condicoes.payload_a(prefixos[0], 1), ensure_ascii=False, indent=2))
    return 0


def _cmd_rodar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    alvo = tuple(c.strip().upper() for c in args.condicoes.split(",") if c.strip())
    desconhecidas = [c for c in alvo if c not in condicoes.CONDICOES]
    if desconhecidas:
        raise SystemExit(
            f"condição desconhecida: {', '.join(desconhecidas)} "
            f"(use {', '.join(condicoes.CONDICOES)})"
        )
    # As três condições saem do mesmo serviço: basta o artefato de pé.
    cfg.exige_artefato()

    prefixos = [
        p
        for item in itens
        for p in expandir_prefixos(item, com_pressao=not args.sem_pressao)
    ]
    if args.limite:
        prefixos = prefixos[: args.limite]

    tarefas = montar_tarefas(prefixos, condicoes_alvo=alvo, execucoes=args.execucoes, semente=args.semente)
    if args.simular:
        # B só nos prefixos de pressão, por isso a conta não é um produto simples.
        por_condicao = Counter(condicao for _, condicao, _ in tarefas)
        detalhe = ", ".join(f"{c}: {n}" for c, n in sorted(por_condicao.items()))
        print(
            f"{len(tarefas)} chamadas planejadas ({len(prefixos)} prefixos × "
            f"{args.execucoes} execuções — {detalhe})"
        )
        return 0

    # Conferência que antecede a corrida: de que prompts saem estes turnos.
    hashes = condicoes.hashes_do_servico(cfg)
    id_execucao = args.execucao or novo_id_execucao()
    diretorio = diretorio_execucao(id_execucao)
    atualizar_manifesto(
        diretorio,
        {
            "id_execucao": id_execucao,
            "api_base": cfg.api_base,
            "modelo_base": cfg.modelo_base,
            "condicoes": list(alvo),
            "execucoes_por_prefixo": args.execucoes,
            "semente": args.semente,
            "prefixos": len(prefixos),
            "itens": [item["id"] for item in itens],
            "hash_prompt_socratic": hashes["prompt_socratic"],
            "hash_prompt_neutral": hashes["prompt_neutral"],
            "hash_contexto": hashes["contexto"],
            "hash_enunciado": hashes["enunciado"],
            "hash_prompt_juiz": juiz.hash_prompt(),
            "commit_maieutica": commit_atual(Path(__file__).resolve().parent.parent),
        },
    )
    print(f"execução {id_execucao} → {diretorio}")
    print(f"{len(tarefas)} chamadas planejadas; paralelismo {cfg.paralelismo}")

    feitos = {"n": 0}

    def progresso(_registro: dict[str, Any]) -> None:
        feitos["n"] += 1
        if feitos["n"] % 10 == 0 or feitos["n"] == len(tarefas):
            print(f"  {feitos['n']}/{len(tarefas)}", flush=True)

    resumo = executar(
        cfg,
        prefixos,
        diretorio,
        condicoes_alvo=alvo,
        execucoes=args.execucoes,
        reexecucoes=args.reexecucoes,
        semente=args.semente,
        ao_terminar=progresso,
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


def _cmd_julgar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    cfg.exige_juiz()
    diretorio = diretorio_execucao(args.execucao, criar=False)
    if not diretorio.is_dir():
        raise SystemExit(f"execução não encontrada: {diretorio}")

    _conferir_modelo_do_juiz(cfg)
    distinta = juiz.familia_distinta(cfg.juiz_modelo, cfg.modelo_base)
    if not distinta:
        print(
            f"AVISO: juiz ({cfg.juiz_modelo}, família {juiz.familia_do_modelo(cfg.juiz_modelo)}) "
            f"não é de família distinta da do tutor ({cfg.modelo_base}). Serve para ensaio "
            "técnico; o manifesto grava juiz_familia_distinta: false. Para a corrida reportável, "
            f"`--juiz-protocolo` ({JUIZ_MODELO_PROTOCOLO})."
        )
    atualizar_manifesto(
        diretorio,
        {
            "juiz_transporte": cfg.juiz_provedor,
            "juiz_modelo": cfg.juiz_modelo,
            "juiz_familia": juiz.familia_do_modelo(cfg.juiz_modelo),
            "juiz_familia_distinta": distinta,
            "hash_prompt_juiz": juiz.hash_prompt(),
        },
    )
    print(f"juiz: {cfg.juiz_modelo} via {cfg.juiz_provedor}")
    resumo = julgar_execucao(
        cfg,
        diretorio,
        itens,
        incluir_referencia=not args.sem_referencia,
        limite=args.limite,
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0 if resumo["erros"] == 0 else 1


def _conferir_modelo_do_juiz(cfg: Config) -> None:
    """Falha cedo quando o proxy não encaminha o modelo pedido, em vez de errar 13 vezes."""
    if cfg.juiz_provedor != "litellm":
        return
    try:
        disponiveis = juiz.listar_modelos(cfg)
    except SystemExit:
        return
    if disponiveis and cfg.juiz_modelo not in disponiveis:
        raise SystemExit(
            f"o proxy não encaminha o modelo {cfg.juiz_modelo!r} para esta chave.\n"
            f"disponíveis: {', '.join(disponiveis)}\n"
            "Peça a inclusão de um modelo Gemini na chave do LiteLLM (o protocolo exige família "
            "distinta da do tutor) ou use JUIZ_PROVEDOR=gemini com GEMINI_API_KEY."
        )


def _cmd_analisar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    diretorio = diretorio_execucao(args.execucao, criar=False)
    if not diretorio.is_dir():
        raise SystemExit(f"execução não encontrada: {diretorio}")
    resumo = analise.analisar(diretorio, itens, juiz_modelo=args.juiz_modelo)
    print((diretorio / "analise" / "resumo.md").read_text(encoding="utf-8"))
    print(f"tabelas e CSVs em {diretorio / 'analise'}")
    return 0 if resumo else 1


def _cmd_amostra(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    diretorio = diretorio_execucao(args.execucao, criar=False)
    resumo = validacao_humana.gerar_amostra(
        diretorio, itens, tamanho=args.tamanho, tamanho_referencia=args.tamanho_referencia
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


def _cmd_kappa(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    diretorio = diretorio_execucao(args.execucao, criar=False)
    resultado = validacao_humana.calcular_kappa(diretorio, itens)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    if resultado["recodificacao_pendente"]:
        print(
            f"recodificação ainda por preencher ({validacao_humana.ARQUIVO_RECODIFICACAO}): o κ "
            f"intra-avaliador exige a segunda rodada, decorridas ao menos "
            f"{validacao_humana.INTERVALO_MINIMO_SEMANAS} semanas.",
        )
    if resultado["indefinidos"]:
        print(
            "κ indefinido (uma só categoria na subamostra) em: "
            + ", ".join(resultado["indefinidos"])
            + " — não é aceitação.",
        )
    return 0 if resultado["validadas"] else 1


def _cmd_juiz_modelos(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    cfg.exige_juiz()
    for modelo in juiz.listar_modelos(cfg):
        print(modelo)
    return 0


def _hashes_congelados(cfg: Config, diretorio: Path) -> dict[str, str]:
    """Relê os hashes do serviço; se já estiver desligado, mantém os que a corrida gravou."""
    manifesto = ler_json(diretorio / "manifesto.json")
    anteriores = {
        chave: manifesto.get(chave, "")
        for chave in ("hash_prompt_socratic", "hash_prompt_neutral", "hash_contexto", "hash_enunciado")
    }
    try:
        atuais = condicoes.hashes_do_servico(cfg)
    except SystemExit:
        print("AVISO: serviço indisponível; mantendo os hashes gravados na corrida.")
        return anteriores
    novos = {
        "hash_prompt_socratic": atuais["prompt_socratic"],
        "hash_prompt_neutral": atuais["prompt_neutral"],
        "hash_contexto": atuais["contexto"],
        "hash_enunciado": atuais["enunciado"],
    }
    divergentes = [k for k, v in novos.items() if anteriores.get(k) and anteriores[k] != v]
    if divergentes:
        raise SystemExit(
            "o serviço mudou desde a corrida: "
            + ", ".join(divergentes)
            + ". Os turnos gravados não foram gerados por este prompt — não congele."
        )
    return novos


def _cmd_exportar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    """Emparelhamento gerado × referências para as métricas de sobreposição (código original)."""
    diretorio = diretorio_execucao(args.execucao, criar=False)
    if not diretorio.is_dir():
        raise SystemExit(f"execução não encontrada: {diretorio}")
    resumo = exportacao.exportar_sobreposicao(diretorio, itens)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


def _cmd_congelar(args, cfg: Config, itens: list[dict[str, Any]]) -> int:
    """Registra o que a reprodutibilidade exige, lido do que foi de facto executado."""
    diretorio = diretorio_execucao(args.execucao, criar=False)
    raiz = Path(__file__).resolve().parent.parent
    turnos = list(ler_ndjson(diretorio / ARQUIVO_TURNOS))
    juizos = list(ler_ndjson(diretorio / ARQUIVO_JUIZOS))
    manifesto = atualizar_manifesto(
        diretorio,
        {
            "congelado": True,
            "commit_maieutica": commit_atual(raiz),
            "commit_ide": commit_atual(raiz.parent / "portugol-ai-tutor"),
            "commit_tese": commit_atual(raiz.parent / "Tese"),
            **_hashes_congelados(cfg, diretorio),
            "hash_prompt_juiz": juiz.hash_prompt(),
            # Versões como a API as devolveu, não como foram pedidas.
            "modelos_observados": sorted({t.get("modelo", "") for t in turnos if t.get("modelo")}),
            "juiz_observado": sorted(
                {
                    f"{j.get('juiz_transporte', '')}:{j.get('juiz_versao') or j.get('juiz_modelo', '')}"
                    for j in juizos
                    if not j.get("erro")
                }
            ),
            "turnos_registrados": len(turnos),
            "juizos_registrados": sum(1 for j in juizos if not j.get("erro")),
        },
    )
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- infraestrutura


def _config(args) -> Config:
    """Precedência do modelo do juiz: --juiz-modelo > --juiz-protocolo > JUIZ_MODELO > padrão."""
    cfg = Config()
    ajustes: dict[str, Any] = {}
    if getattr(args, "api_base", None):
        ajustes["api_base"] = args.api_base
    if getattr(args, "paralelismo", None):
        ajustes["paralelismo"] = args.paralelismo
    if getattr(args, "juiz_protocolo", False):
        ajustes["juiz_modelo"] = JUIZ_MODELO_PROTOCOLO
    if getattr(args, "juiz_modelo", None):
        ajustes["juiz_modelo"] = args.juiz_modelo
    if getattr(args, "juiz_provedor", None):
        ajustes["juiz_provedor"] = args.juiz_provedor
    return Config(**{**cfg.__dict__, **ajustes}) if ajustes else cfg


def _itens(args) -> list[dict[str, Any]]:
    itens = carregar_banco(Path(args.banco))
    if not itens:
        raise SystemExit(f"nenhum item em {args.banco}")
    if getattr(args, "itens", ""):
        escolhidos = {i.strip() for i in args.itens.split(",") if i.strip()}
        itens = [item for item in itens if item["id"] in escolhidos]
        if not itens:
            raise SystemExit(f"nenhum item casa com {sorted(escolhidos)}")
    return itens


def _parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--banco", default=str(BANCO_DIR), help="diretório do banco de itens")
    comum.add_argument("--itens", default="", help="ids separados por vírgula")

    principal = argparse.ArgumentParser(
        prog="avaliacao", description=__doc__, parents=[comum],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = principal.add_subparsers(dest="comando", required=True)

    importar = sub.add_parser(
        "importar",
        help="gera rascunhos de item a partir do conjunto de Al-Hossami (tradução à parte)",
        parents=[comum],
    )
    importar.add_argument("--fonte", required=True, help="diretório v2_sigcse/final_dataset do conjunto original")
    importar.add_argument("--dialogo", default="", help="prefixo do nome do diálogo; vazio importa todos")
    importar.add_argument("--saida", default=str(TRADUCAO_DIR), help="diretório dos rascunhos")
    importar.set_defaults(funcao=_cmd_importar)

    validar = sub.add_parser("validar", help="valida o banco de itens", parents=[comum])
    validar.set_defaults(funcao=_cmd_validar)

    estados = sub.add_parser("estados", help="pré-computa erros do compilador e casos de teste (usa o motor da IDE)", parents=[comum])
    estados.add_argument("--runner", default="", help="caminho de packages/runner/lib/headless/cli.js")
    estados.set_defaults(funcao=_cmd_estados)

    prefixos = sub.add_parser("prefixos", help="lista os prefixos que seriam enviados", parents=[comum])
    prefixos.add_argument("--json", action="store_true")
    prefixos.add_argument("--payload", action="store_true", help="mostra um corpo de requisição")
    prefixos.set_defaults(funcao=_cmd_prefixos)

    rodar = sub.add_parser("rodar", help="executa a bancada nas condições escolhidas", parents=[comum])
    rodar.add_argument("--execucao", default="", help="id da execução (retoma se já existir)")
    rodar.add_argument("--condicoes", default=",".join(condicoes.CONDICOES))
    rodar.add_argument("--execucoes", type=int, default=EXECUCOES_PADRAO)
    rodar.add_argument("--reexecucoes", type=int, default=REEXECUCOES_PADRAO)
    rodar.add_argument("--sem-pressao", action="store_true")
    rodar.add_argument("--limite", type=int, default=0, help="usa só os N primeiros prefixos")
    rodar.add_argument("--semente", type=int, default=20260912)
    rodar.add_argument("--simular", action="store_true", help="conta as chamadas e sai")
    rodar.add_argument("--api-base", default="")
    rodar.add_argument("--paralelismo", type=int, default=0)
    rodar.set_defaults(funcao=_cmd_rodar)

    julgar = sub.add_parser("julgar", help="classifica os turnos com o juiz automático", parents=[comum])
    julgar.add_argument("--execucao", default="")
    julgar.add_argument("--limite", type=int, default=None)
    julgar.add_argument("--sem-referencia", action="store_true")
    julgar.add_argument(
        "--juiz-protocolo",
        action="store_true",
        help=f"usa o modelo do protocolo ({JUIZ_MODELO_PROTOCOLO}): família distinta da do tutor, "
        "necessário para resultado reportável, e mais caro",
    )
    julgar.add_argument("--juiz-modelo", default="", help="modelo específico (tem precedência)")
    julgar.add_argument(
        "--juiz-provedor", default="", choices=["", "litellm", "gemini", "openai"],
        help="transporte do juiz: litellm (mesma autenticação do tutor) ou gemini (API da Google)",
    )
    julgar.add_argument("--paralelismo", type=int, default=0)
    julgar.set_defaults(funcao=_cmd_julgar)

    analisar = sub.add_parser("analisar", help="gera H1, H2, descritivas e tabelas", parents=[comum])
    analisar.add_argument("--execucao", default="")
    analisar.add_argument(
        "--juiz-modelo", default="", help="analisa os juízos deste modelo (padrão: o do manifesto)"
    )
    analisar.set_defaults(funcao=_cmd_analisar)

    exportar = sub.add_parser(
        "exportar",
        help="emparelhamento gerado × referências para BLEU-4/ROUGE-L/BERTScore",
        parents=[comum],
    )
    exportar.add_argument("--execucao", default="")
    exportar.set_defaults(funcao=_cmd_exportar)

    amostra = sub.add_parser("amostra-humana", help="planilhas cegas para o codificador único", parents=[comum])
    amostra.add_argument("--execucao", default="")
    amostra.add_argument("--tamanho", type=int, default=validacao_humana.TAMANHO_GERADOS,
                         help="turnos gerados na planilha (~150 + ~30 pela condição B)")
    amostra.add_argument("--tamanho-referencia", type=int,
                         default=validacao_humana.TAMANHO_REFERENCIA,
                         help="turnos de referência humanos, na mesma planilha cega")
    amostra.set_defaults(funcao=_cmd_amostra)

    kappa = sub.add_parser("kappa", help="concordância intra-avaliador e com o juiz", parents=[comum])
    kappa.add_argument("--execucao", default="")
    kappa.set_defaults(funcao=_cmd_kappa)

    modelos = sub.add_parser("juiz-modelos", help="lista os modelos visíveis à chave do juiz", parents=[comum])
    modelos.add_argument("--juiz-provedor", default="", choices=["", "litellm", "gemini", "openai"])
    modelos.set_defaults(funcao=_cmd_juiz_modelos)

    congelar = sub.add_parser("congelar", help="registra commits, hashes e modelos no manifesto", parents=[comum])
    congelar.add_argument("--execucao", default="")
    congelar.set_defaults(funcao=_cmd_congelar)
    return principal


if __name__ == "__main__":
    raise SystemExit(main())
