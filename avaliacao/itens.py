"""Banco de itens e expansão em prefixos (Subseções 4.3.1 e 4.3.2 da dissertação).

Um item é um programa em Portugol com defeito conhecido, acompanhado de enunciado, descrição
do defeito, correções aceitas, casos de teste e um diálogo de referência. O formato é o do
*benchmark* de Al-Hossami, acrescido da classe do defeito, dos erros do compilador
pré-computados por estado, dos padrões de correção, dos elementos de ancoragem e do movimento
do estudante anotado em cada turno.

A expansão gera duas famílias de prefixos: os **de referência**, um por posição em que o tutor
anotado fala (turnos anteriores do tutor são os de referência, nunca os gerados, o que impede
propagação de erro entre posições), e os **de pressão**, quatro por item, em que o último turno
do estudante é um pedido explícito de resposta (Apêndice de diretividade).
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

TipoBug = Literal["sintaxe", "logica", "limite", "fluxo_dados", "tipo", "laco_infinito"]
Movimento = Literal["PROGRESSO", "ESTAGNACAO", "REGRESSAO", "PEDIDO_EXPLICITO", "NENHUM"]

TIPOS_BUG = ("sintaxe", "logica", "limite", "fluxo_dados", "tipo", "laco_infinito")
ORIGENS = ("al_hossami_v2", "tese")
MOVIMENTOS = ("PROGRESSO", "ESTAGNACAO", "REGRESSAO", "PEDIDO_EXPLICITO", "NENHUM")

#: Frases de pressão, literais do Apêndice de diretividade. Sorteadas sem reposição por item.
FRASES_PRESSAO: tuple[str, ...] = (
    "Não entendi. Me fala logo o que está errado.",
    "Já tentei de tudo, não consigo. Pode me mandar o código certo?",
    "Só me diz qual linha eu tenho que mudar.",
    "Não tenho tempo pra isso, qual é a resposta?",
    "Me mostra como fica o código arrumado, por favor.",
)

#: Semente do sorteio das frases: fixa, para que a expansão seja reproduzível.
SEMENTE_PRESSAO = "maieutica-bancada-v1"


@dataclass(frozen=True)
class Prefixo:
    """Uma unidade de amostragem da bancada: item × posição, pronta para virar requisição."""

    id: str
    item_id: str
    origem: str
    tipo_bug: str
    prioridade: int
    k: int
    tipo: Literal["ouro", "pressao"]
    posicao_pressao: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    problem_statement: str = ""
    code: str = ""
    errors: list[str] = field(default_factory=list)
    compiler_error_lines: list[int] = field(default_factory=list)
    previous_code: str | None = None
    previous_errors: list[str] | None = None
    estado_codigo: str = ""
    #: Classes de defeito ainda presentes no estado vigente. O diagnóstico do analista é
    #: pontuado contra elas, não contra a classe do item: quatro dos seis itens têm mais de um
    #: defeito, e a classe catalogada descreve só o primeiro.
    defeitos_vigentes: list[str] = field(default_factory=list)
    movimento_anterior: str = "NENHUM"
    estagnacao_acumulada: int = 0
    referencia: str = ""
    alternativas: list[str] = field(default_factory=list)

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)


def carregar_banco(diretorio: Path) -> list[dict[str, Any]]:
    """Lê todos os itens ``*.json`` do diretório, em ordem estável por ``id``."""
    itens = []
    for caminho in sorted(diretorio.glob("*.json")):
        item = json.loads(caminho.read_text(encoding="utf-8"))
        item.setdefault("_arquivo", caminho.name)
        itens.append(item)
    return sorted(itens, key=lambda it: it.get("id", ""))


def validar_item(item: dict[str, Any]) -> list[str]:
    """Devolve a lista de problemas do item; vazia significa item válido."""
    erros: list[str] = []
    ident = item.get("id") or "<sem id>"

    for campo in ("id", "origem", "tipo_bug", "problem", "bug_code", "bug_desc"):
        if not str(item.get(campo, "")).strip():
            erros.append(f"{ident}: campo obrigatório vazio: {campo}")
    if item.get("origem") not in ORIGENS:
        erros.append(f"{ident}: origem inválida: {item.get('origem')!r} (use {ORIGENS})")
    if item.get("tipo_bug") not in TIPOS_BUG:
        erros.append(f"{ident}: tipo_bug inválido: {item.get('tipo_bug')!r} (use {TIPOS_BUG})")
    if not item.get("bug_fixes"):
        erros.append(f"{ident}: bug_fixes vazio")

    estados = {e.get("id"): e for e in item.get("estados_codigo", [])}
    if not estados:
        erros.append(f"{ident}: estados_codigo vazio (é preciso ao menos o estado inicial)")
    for chave, estado in estados.items():
        if not str(estado.get("codigo", "")).strip():
            erros.append(f"{ident}: estado {chave} sem código")
        if not isinstance(estado.get("errors", []), list):
            erros.append(f"{ident}: estado {chave}: errors deve ser lista")
        if not isinstance(estado.get("compilerErrorLines", []), list):
            erros.append(f"{ident}: estado {chave}: compilerErrorLines deve ser lista")
        erros.extend(_validar_defeitos_vigentes(item, ident, chave, estado))

    dialogo = item.get("dialogo", [])
    if not dialogo:
        erros.append(f"{ident}: diálogo vazio")
    elif dialogo[0].get("papel") != "estudante":
        erros.append(f"{ident}: o diálogo abre com o estudante, por protocolo")
    vistos_estudante = 0
    for pos, turno in enumerate(dialogo):
        papel = turno.get("papel")
        if papel not in ("estudante", "tutor"):
            erros.append(f"{ident}: turno {pos}: papel inválido {papel!r}")
            continue
        if not str(turno.get("texto", "")).strip():
            erros.append(f"{ident}: turno {pos}: texto vazio")
        if papel == "estudante":
            vistos_estudante += 1
            estado = turno.get("estado_codigo")
            if estado is not None and estado not in estados:
                erros.append(f"{ident}: turno {pos}: estado_codigo {estado!r} não existe")
            movimento = turno.get("movimento", "NENHUM")
            if movimento not in MOVIMENTOS:
                erros.append(f"{ident}: turno {pos}: movimento inválido {movimento!r}")
            if vistos_estudante == 1 and movimento != "NENHUM":
                erros.append(f"{ident}: turno {pos}: o turno de abertura não recebe movimento")

    erros.extend(_validar_estados_usados(item, ident, estados))
    erros.extend(_validar_fix_patterns(item, ident))

    ancoras = item.get("anchor_tokens", {})
    if not isinstance(ancoras, dict) or not any(
        ancoras.get(chave) for chave in ("linhas", "variaveis", "construtos")
    ):
        erros.append(f"{ident}: anchor_tokens precisa de linhas, variáveis ou construtos")
    return erros


def _validar_defeitos_vigentes(
    item: dict[str, Any], ident: str, chave: Any, estado: dict[str, Any]
) -> list[str]:
    """Todo estado declara que classes de defeito ainda estão nele.

    É contra essa lista, e não contra a classe catalogada do item, que o diagnóstico do analista
    é pontuado: quatro dos seis itens têm mais de um defeito, e nos estados em que o primeiro já
    foi corrigido a classe do item deixa de descrever o que o estudante tem à frente.
    """
    vigentes = estado.get("defeitos_vigentes")
    if vigentes is None:
        return [f"{ident}: estado {chave} sem defeitos_vigentes"]
    if not isinstance(vigentes, list):
        return [f"{ident}: estado {chave}: defeitos_vigentes deve ser lista"]
    invalidos = [c for c in vigentes if c not in TIPOS_BUG]
    if invalidos:
        return [f"{ident}: estado {chave}: classe inválida em defeitos_vigentes: {invalidos}"]
    if chave == item.get("estado_solucao") and vigentes:
        return [f"{ident}: estado_solucao {chave} não pode ter defeito vigente: {vigentes}"]
    if chave != item.get("estado_solucao") and not vigentes:
        return [f"{ident}: estado {chave} sem defeito vigente, mas não é a solução declarada"]
    return []


def _validar_estados_usados(
    item: dict[str, Any], ident: str, estados: dict[Any, dict[str, Any]]
) -> list[str]:
    """Todo estado pré-computado é usado: ou um turno vive nele, ou é a solução declarada.

    Um estado órfão significa que algum turno aponta para o estado errado — o defeito que se
    mede deixa de ser o defeito que o estudante tem à frente. O estado terminal, em que as
    correções aceitas já estão todas aplicadas, não aparece no diálogo por construção e é
    declarado em ``estado_solucao``.
    """
    erros: list[str] = []
    solucao = item.get("estado_solucao")
    if solucao is not None:
        if solucao not in estados:
            erros.append(f"{ident}: estado_solucao {solucao!r} não existe")
        else:
            estado = estados[solucao]
            total = estado.get("casos_total")
            if total and estado.get("casos_ok") != total:
                erros.append(
                    f"{ident}: estado_solucao {solucao!r} não passa em todos os casos de teste "
                    f"({estado.get('casos_ok')}/{total})"
                )

    usados = {
        turno.get("estado_codigo")
        for turno in item.get("dialogo", [])
        if turno.get("papel") == "estudante" and turno.get("estado_codigo") is not None
    }
    usados.add(solucao)
    for chave in estados:
        if chave not in usados:
            erros.append(
                f"{ident}: estado {chave} não é usado por nenhum turno nem é o estado_solucao"
            )
    return erros


def _validar_fix_patterns(item: dict[str, Any], ident: str) -> list[str]:
    """Padrões de correção: têm de casar as correções aceitas e nenhuma referência.

    A regra é a do Apêndice de diretividade: as regex são derivadas das correções aceitas e
    validadas contra as alternativas de referência — nenhuma delas pode dispará-las, sob pena
    de o detector objetivo acusar revelação num turno que os anotadores julgaram socrático.

    O outro sentido também é verificado: um padrão que já case o **código inicial** não
    distingue a correção do defeito e acusaria revelação em qualquer turno que cite a linha
    corrente do estudante. Um padrão satisfeito por um estado posterior é legítimo (a correção
    já foi aplicada) e quem o ignora, aí, é o detector, que conhece o código vigente do prefixo.
    """
    padroes = item.get("fix_patterns", [])
    if not padroes:
        return [f"{ident}: fix_patterns vazio (sem detector objetivo de nível 3)"]

    erros: list[str] = []
    compilados: list[re.Pattern[str]] = []
    for bruto in padroes:
        try:
            compilados.append(re.compile(bruto, re.IGNORECASE))
        except re.error as exc:
            erros.append(f"{ident}: fix_pattern inválida {bruto!r}: {exc}")

    correcoes = "\n".join(item.get("bug_fixes", []))
    for padrao in compilados:
        if not padrao.search(correcoes):
            erros.append(
                f"{ident}: fix_pattern {padrao.pattern!r} não casa nenhuma correção aceita"
            )

    estados = {e.get("id"): e for e in item.get("estados_codigo", [])}
    inicial = (estados.get("s0") or {}).get("codigo") or item.get("bug_code", "")
    for padrao in compilados:
        if padrao.search(inicial):
            erros.append(
                f"{ident}: fix_pattern {padrao.pattern!r} já casa o código inicial — "
                "não distingue a correção do defeito"
            )

    for pos, turno in enumerate(item.get("dialogo", [])):
        if turno.get("papel") != "tutor":
            continue
        for texto in [turno.get("texto", "")] + list(turno.get("alternativas", [])):
            for padrao in compilados:
                if padrao.search(texto):
                    erros.append(
                        f"{ident}: turno {pos}: referência dispara fix_pattern "
                        f"{padrao.pattern!r} — a regex é larga demais"
                    )
    return erros


def movimento_objetivo(anterior: dict[str, Any], atual: dict[str, Any]) -> str | None:
    """Regra objetiva do movimento entre dois estados (Subseção de variáveis da metodologia).

    Progresso se o erro de compilação desapareceu ou mais casos passam; regressão se surgiu erro
    de compilação ou menos casos passam; estagnação se nada mudou.

    O programa deixar de estourar o tempo conta como progresso (e voltar a estourar, como
    regressão): num item da classe ``laco_infinito`` o laço parar de correr para sempre é a
    mudança objetiva do estado, e ela é invisível à contagem de casos, que continua em zero
    enquanto a saída estiver errada.
    """
    erros_antes = len(anterior.get("errors", []))
    erros_depois = len(atual.get("errors", []))
    sem_evidencia = (
        not erros_antes
        and not erros_depois
        and anterior.get("casos_ok") is None
        and atual.get("casos_ok") is None
        and not anterior.get("timeout")
        and not atual.get("timeout")
    )
    if sem_evidencia:
        # Estados ainda não pré-computados (`estados` não rodou): a regra não tem o que ler.
        return None
    if erros_antes and not erros_depois:
        return "PROGRESSO"
    if erros_depois and not erros_antes:
        return "REGRESSAO"
    if anterior.get("timeout") and not atual.get("timeout"):
        return "PROGRESSO"
    if atual.get("timeout") and not anterior.get("timeout"):
        return "REGRESSAO"
    ok_antes, ok_depois = anterior.get("casos_ok"), atual.get("casos_ok")
    if ok_antes is not None and ok_depois is not None:
        if ok_depois > ok_antes:
            return "PROGRESSO"
        if ok_depois < ok_antes:
            return "REGRESSAO"
    if erros_depois < erros_antes:
        return "PROGRESSO"
    if erros_depois > erros_antes:
        return "REGRESSAO"
    return "ESTAGNACAO"


def avisos_item(item: dict[str, Any]) -> list[str]:
    """Divergências que não invalidam o item mas o revisor tem de ver.

    A anotação de movimento e a regra objetiva dos estados podem discordar; quando há edição de
    código, é a regra objetiva que a medida usa, e a discordância é um candidato a erro de
    anotação. Sem edição decide o texto, e aí a nota serve só para o revisor confirmar que a
    leitura textual foi deliberada.
    """
    estados = {e.get("id"): e for e in item.get("estados_codigo", [])}
    ident = item.get("id") or "<sem id>"
    avisos: list[str] = []
    anterior: dict[str, Any] | None = None
    id_anterior = ""

    for pos, turno in enumerate(item.get("dialogo", [])):
        if turno.get("papel") != "estudante":
            continue
        atual = estados.get(turno.get("estado_codigo"))
        movimento = turno.get("movimento", "NENHUM")
        if atual is None or anterior is None:
            anterior, id_anterior = atual or anterior, turno.get("estado_codigo") or id_anterior
            continue
        id_atual = turno.get("estado_codigo")
        if anterior.get("codigo") != atual.get("codigo"):
            objetivo = movimento_objetivo(anterior, atual)
            if objetivo is not None and movimento != objetivo:
                avisos.append(
                    f"{ident}: turno {pos}: movimento anotado {movimento}, mas a regra objetiva "
                    f"diz {objetivo} ({id_anterior}→{id_atual}: erros "
                    f"{len(anterior.get('errors', []))}→{len(atual.get('errors', []))}, casos "
                    f"{anterior.get('casos_ok')}→{atual.get('casos_ok')}) — com edição de código, "
                    "é a regra objetiva que a medida usa"
                )
        elif movimento in ("PROGRESSO", "REGRESSAO"):
            avisos.append(
                f"{ident}: turno {pos}: movimento anotado {movimento} sem edição de código "
                f"({id_anterior}→{id_atual}) — decidido pelo texto; confirme que é deliberado"
            )
        anterior, id_anterior = atual, id_atual

    avisos.extend(_avisos_pos_solucao(item, ident, estados))
    return avisos


def _avisos_pos_solucao(
    item: dict[str, Any], ident: str, estados: dict[Any, dict[str, Any]]
) -> list[str]:
    """Turnos do tutor que ocorrem com o defeito já corrigido.

    Cada um vira um prefixo-ouro em que não há mais o que depurar: no conjunto original são
    cortesia de encerramento ("muito bem", "de nada"), e a diretividade medida ali não fala
    da política de intervenção. Os itens da dissertação terminam no último turno substantivo do
    tutor e declaram a solução em ``estado_solucao``, sem narrá-la no diálogo.
    """
    solucao = item.get("estado_solucao")
    if solucao not in estados:
        return []
    dialogo = item.get("dialogo", [])
    corte = next(
        (i for i, t in enumerate(dialogo)
         if t.get("papel") == "estudante" and t.get("estado_codigo") == solucao),
        None,
    )
    if corte is None:
        return []
    tutores = [i for i, t in enumerate(dialogo[corte:], start=corte) if t.get("papel") == "tutor"]
    if not tutores:
        return []
    return [
        f"{ident}: {len(tutores)} turno(s) do tutor (posições {tutores}) ocorrem depois de o "
        f"estudante alcançar {solucao}, o estado_solucao — viram prefixos-ouro sem defeito a "
        "depurar; confirme que é deliberado"
    ]


def expandir_prefixos(
    item: dict[str, Any], *, com_pressao: bool = True, semente: str = SEMENTE_PRESSAO
) -> list[Prefixo]:
    """Gera os prefixos de referência e os de pressão de um item."""
    prefixos = [p for p in _prefixos_ouro(item)]
    if com_pressao:
        prefixos.extend(_prefixos_pressao(item, semente))
    return prefixos


def _prefixos_ouro(item: dict[str, Any]) -> Iterable[Prefixo]:
    dialogo = item.get("dialogo", [])
    k = 0
    for pos, turno in enumerate(dialogo):
        if turno.get("papel") != "tutor":
            continue
        k += 1
        contexto = _contexto(item, dialogo[:pos])
        yield Prefixo(
            id=f"{item['id']}::k{k}::ouro",
            item_id=item["id"],
            origem=item["origem"],
            tipo_bug=item["tipo_bug"],
            prioridade=int(item.get("prioridade", 1)),
            k=k,
            tipo="ouro",
            referencia=turno.get("texto", ""),
            alternativas=list(turno.get("alternativas", [])),
            **contexto,
        )


def _prefixos_pressao(item: dict[str, Any], semente: str) -> Iterable[Prefixo]:
    """Dois após o primeiro turno do tutor e dois após o terceiro — quatro, quando o diálogo dá.

    Com menos de três turnos do tutor, "tarde" é o último turno disponível; quando esse último
    **é** o primeiro, as duas âncoras seriam a mesma posição e o rótulo ``posicao_pressao``
    passaria a mentir na análise por posição. Nesse caso o item rende só os dois prefixos de
    "cedo": é preferível menos pressão a um contraste de posição que não existe.
    """
    dialogo = item.get("dialogo", [])
    posicoes_tutor = [pos for pos, t in enumerate(dialogo) if t.get("papel") == "tutor"]
    if not posicoes_tutor:
        return

    sorteio = random.Random(f"{semente}:{item['id']}")
    frases = sorteio.sample(list(FRASES_PRESSAO), k=min(4, len(FRASES_PRESSAO)))

    cedo = posicoes_tutor[0]
    tarde = posicoes_tutor[2] if len(posicoes_tutor) >= 3 else posicoes_tutor[-1]
    ancoras = [("cedo", cedo)] + ([("tarde", tarde)] if tarde != cedo else [])
    indice = 0
    for rotulo, pos_tutor in ancoras:
        for repeticao in (1, 2):
            if indice >= len(frases):
                return
            frase = frases[indice]
            indice += 1
            prefixo_turnos = list(dialogo[: pos_tutor + 1])
            contexto = _contexto(item, prefixo_turnos)
            # A frase de pressão não edita código: herda o estado vigente, como qualquer turno
            # sem edição. Sem ele o serviço não reclassifica o histórico e o contador degrada.
            contexto["history"] = contexto["history"] + [{
                "role": "user",
                "content": frase,
                "code": contexto["code"],
                "errors": list(contexto["errors"]),
            }]
            contexto["movimento_anterior"] = "PEDIDO_EXPLICITO"
            k = sum(1 for t in prefixo_turnos if t.get("papel") == "tutor") + 1
            yield Prefixo(
                id=f"{item['id']}::k{k}::pressao_{rotulo}_{repeticao}",
                item_id=item["id"],
                origem=item["origem"],
                tipo_bug=item["tipo_bug"],
                prioridade=int(item.get("prioridade", 1)),
                k=k,
                tipo="pressao",
                posicao_pressao=rotulo,
                **contexto,
            )


def _contexto(item: dict[str, Any], turnos: list[dict[str, Any]]) -> dict[str, Any]:
    """Monta ``history``, estado de código vigente e estado anterior a partir do prefixo."""
    estados = {e.get("id"): e for e in item.get("estados_codigo", [])}
    history: list[dict[str, Any]] = []
    estados_vistos: list[dict[str, Any]] = []
    movimento = "NENHUM"
    acumulada = 0
    inicial = estados.get("s0") or {"codigo": item["bug_code"], "errors": [], "compilerErrorLines": []}
    estado_corrente = inicial

    for indice, turno in enumerate(turnos):
        texto = turno.get("texto", "")
        if turno.get("papel") == "estudante":
            # O enunciado NÃO entra aqui: vai em ``problem_statement``, campo próprio do pedido.
            # Colado ao primeiro conteúdo do usuário, ele era lido como fala do estudante por
            # toda análise textual do movimento — o "corrija" do enunciado casava com o "meu
            # código" do estudante e saía um pedido explícito que nunca houve.
            movimento = turno.get("movimento", "NENHUM")
            if movimento in ("ESTAGNACAO", "REGRESSAO"):
                acumulada += 1
            elif movimento == "PROGRESSO":
                acumulada = 0
            estado = estados.get(turno.get("estado_codigo"))
            if estado is not None:
                estados_vistos.append(estado)
                estado_corrente = estado
            # O estado de código acompanha cada turno do estudante para que o serviço derive a
            # estagnação acumulada do próprio histórico, em vez de a receber pronta. Turno sem
            # estado próprio é turno sem edição: vale o estado corrente, que é o que o
            # estudante tinha à frente quando falou.
            history.append({
                "role": "user",
                "content": texto,
                "code": estado_corrente.get("codigo", ""),
                "errors": list(estado_corrente.get("errors", [])),
            })
        else:
            history.append({"role": "assistant", "content": texto})

    vigente = estados_vistos[-1] if estados_vistos else inicial
    anterior = estados_vistos[-2] if len(estados_vistos) >= 2 else None

    return {
        "history": history,
        "problem_statement": str(item.get("problem", "")),
        "code": vigente.get("codigo", ""),
        "errors": list(vigente.get("errors", [])),
        "compiler_error_lines": list(vigente.get("compilerErrorLines", [])),
        "estado_codigo": vigente.get("id", ""),
        "defeitos_vigentes": list(vigente.get("defeitos_vigentes", [])),
        "previous_code": anterior.get("codigo") if anterior else None,
        "previous_errors": list(anterior.get("errors", [])) if anterior else None,
        "movimento_anterior": movimento,
        "estagnacao_acumulada": acumulada,
    }


def turnos_de_referencia(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Turnos do tutor anotados, com a posição e o movimento que os precede.

    São eles que dão a calibração interna dos limiares (Subseção 4.3.6) e o ``d_{k-1}`` da taxa
    de contingência em bancada.
    """
    dialogo = item.get("dialogo", [])
    saida: list[dict[str, Any]] = []
    k = 0
    for pos, turno in enumerate(dialogo):
        if turno.get("papel") != "tutor":
            continue
        k += 1
        contexto = _contexto(item, dialogo[:pos])
        saida.append(
            {
                "id": f"{item['id']}::k{k}::referencia",
                "item_id": item["id"],
                "k": k,
                "texto": turno.get("texto", ""),
                "movimento_anterior": contexto["movimento_anterior"],
                "estagnacao_acumulada": contexto["estagnacao_acumulada"],
                "history": contexto["history"],
                "code": contexto["code"],
                "errors": contexto["errors"],
            }
        )
    return saida
