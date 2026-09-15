"""A calibração humana dos limiares não pode conter turnos de referência assistidos por modelo.

O defeito que estes testes existem para apanhar não foi a chave errada. Foi uma **exclusão que
reportou 0 sem ninguém reparar**: `apurar_h1_h2.referencias()` lia
`j["contexto"]["referencia_autoria"]`, não há chave `contexto` em veredito nenhum,
`.get("contexto", {})` devolvia `{}`, o `or` caía no valor humano e o filtro passava os 140
turnos `autor_com_assistencia` de `cap5` para dentro do padrão humano — imprimindo «0 excluídos»
como se fosse medida. `avaliacao.analise._taxas_referencia` não filtrava de todo, e é ela que
gera `resumo.md` e `tab_5_3_h1.tex`, ambos rotulados «turnos de referência humanos».

É a mesma família do manifesto a gravar proxies do estado: uma verificação que passa em silêncio.
Por isso o teste que manda é :func:`test_exclusao_bate_com_o_banco_em_cada_execucao`, que confere
a exclusão contra o **banco** — fonte independente da chave que o filtro lê. Contar as exclusões
pela própria chave do filtro não prova nada: era exatamente o que o código partido fazia.

Zero excluídos é legítimo só quando o banco também diz zero (é o caso de `cap4`). Com turnos
assistidos presentes, excluir zero é falha — e falha alto, não em nota de rodapé.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from avaliacao import analise
from avaliacao.itens import AUTORIA_HUMANA, autoria_referencia

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "avaliacao" / "banco"
EXECUCOES = RAIZ / "avaliacao" / "execucoes"

#: Execuções com artefato completo. As de ensaio não têm `juizos.jsonl` e não entram.
COM_ARTEFATO = [d.name for d in sorted(EXECUCOES.glob("*")) if (d / "juizos.jsonl").is_file()]


def _itens_do_banco() -> dict[str, dict]:
    itens = {}
    for caminho in sorted(BANCO.glob("*.json")):
        item = json.loads(caminho.read_text(encoding="utf-8"))
        itens[item.get("id", caminho.stem)] = item
    return itens


def _referencias(execucao: str) -> list[dict]:
    caminho = EXECUCOES / execucao / "juizos.jsonl"
    with caminho.open(encoding="utf-8") as arquivo:
        return [j for j in (json.loads(ln) for ln in arquivo if ln.strip())
                if j.get("unidade") == "referencia"]


def _juizos_por_chave(registros: list[dict]) -> dict[str, dict]:
    return {j["chave"]: j for j in registros}


# --------------------------------------------------------------- o teste que manda


@pytest.mark.parametrize("execucao", COM_ARTEFATO)
def test_exclusao_bate_com_o_banco_em_cada_execucao(execucao: str) -> None:
    """A exclusão medida contra o banco, que é a fonte independente da chave do filtro."""
    itens = _itens_do_banco()
    refs = _referencias(execucao)
    assert refs, f"execução `{execucao}` sem turnos de referência"

    assistidos_no_banco = [j for j in refs
                           if autoria_referencia(itens.get(j["item_id"], {})) != AUTORIA_HUMANA]
    taxas = analise._taxas_referencia(_juizos_por_chave(refs), itens)
    entraram = taxas["apos_bloqueio"].total + taxas["apos_progresso"].total

    assert entraram <= len(refs) - len(assistidos_no_banco), (
        f"`{execucao}`: {len(assistidos_no_banco)} de {len(refs)} turnos de referência são de "
        f"autoria assistida segundo o banco, mas a calibração contou {entraram} pares — mais do "
        f"que os turnos humanos permitem. O filtro de autoria está inerte."
    )


@pytest.mark.parametrize("execucao", COM_ARTEFATO)
def test_nenhum_turno_assistido_entra_na_calibracao(execucao: str) -> None:
    """Nenhum `item_id` marcado como assistido no banco pode aparecer na população da REF."""
    itens = _itens_do_banco()
    refs = _referencias(execucao)
    assistidos = {i for i, item in itens.items() if autoria_referencia(item) != AUTORIA_HUMANA}

    # `_taxas_referencia` levanta se a sua própria conta não bater com a do banco; este teste
    # cobre o outro lado, que é a população que sobra ser de facto só a humana.
    humanos = [j for j in refs if str(j.get("referencia_autoria") or AUTORIA_HUMANA) == AUTORIA_HUMANA]
    intrusos = sorted({j["item_id"] for j in humanos} & assistidos)
    assert not intrusos, (
        f"`{execucao}`: itens marcados `autor_com_assistencia` no banco sobreviveram ao filtro "
        f"de autoria: {intrusos}"
    )


# --------------------------------------------------------------- o defeito, reproduzido


def test_filtro_inerte_falha_alto_com_turnos_assistidos_presentes() -> None:
    """Com assistidos presentes, excluir zero tem de rebentar — não passar em silêncio.

    Reproduz a forma exata do defeito: autoria no topo do veredito, e um filtro que a procura
    onde ela não está. Se `_taxas_referencia` voltar a não conferir contra o banco, este teste
    passa a falhar aqui, com a mensagem, em vez de deixar 140 turnos entrarem calados.
    """
    itens = {
        "humano": {"id": "humano", "referencia_autoria": "autor"},
        "assistido": {"id": "assistido", "referencia_autoria": "autor_com_assistencia"},
    }
    registros = []
    for item_id in ("humano", "assistido"):
        for k, (mov, diretividade) in enumerate(
            [("NENHUM", 0), ("ESTAGNACAO", 1), ("ESTAGNACAO", 2)], start=1
        ):
            registros.append({
                "chave": f"{item_id}::k{k}::referencia",
                "unidade": "referencia",
                "item_id": item_id,
                "k": k,
                "movimento_anterior": mov,
                "estagnacao_acumulada": max(0, k - 1),
                "diretividade": diretividade,
                "referencia_autoria": itens[item_id]["referencia_autoria"],
            })

    taxas = analise._taxas_referencia(_juizos_por_chave(registros), itens)
    assert taxas["apos_bloqueio"].total == 2, (
        "só os pares do item humano podem entrar: o item assistido tem de ficar de fora inteiro"
    )

    # E agora a autoria escondida onde o filtro partido a procurava. Nenhum turno traz a chave de
    # topo, logo todos se dizem humanos — e a conta deixa de bater com a do banco.
    escondidos = []
    for registro in registros:
        copia = dict(registro)
        copia["contexto"] = {"referencia_autoria": copia.pop("referencia_autoria")}
        escondidos.append(copia)
    with pytest.raises(AssertionError, match="não confere com o banco"):
        analise._taxas_referencia(_juizos_por_chave(escondidos), itens)
