"""
Movimento do estudante no turno anterior: entrada determinística da política de contingência.

A regra segue a contingência de Wood, Bruner e Ross (1976) na forma operacionalizada pela
dissertação: com edição de código, decide o compilador; sem edição, decide o texto; o pedido
explícito de resposta prevalece sobre as demais categorias. O primeiro turno do estudante, que
abre o diálogo, não recebe movimento: é ``NENHUM``, e a posição 1 do tutor fica fora de H1.

Sem edição, ``PROGRESSO`` exige hipótese ou observação nova — não basta a fala ser longa. "Não
sei", a repetição e a resposta fora do foco são ``ESTAGNACAO``.

A ``REGRESSAO`` textual da dissertação é "hipótese incorreta afirmada". Julgar se uma hipótese
qualquer está errada não cabe a um classificador determinístico, mas uma subclasse cabe: **sem
edição de código, afirmar que o programa está certo é regressão**. O episódio está aberto por
construção — o estudante trouxe um defeito e não mexeu no código —, logo endossar o
comportamento atual é adotar um modelo errado e parar de depurar, e isso se decide pela forma da
fala, não pelo conteúdo da hipótese. Pergunta ("será que está certo?") e hesitação ("não sei se
está certo") não contam. O que sobra — hipótese errada sobre *onde* está o defeito — continua
fora de alcance, fica com a classificação da medida, e a divergência é reportada na análise
estratificada por haver ou não edição de código.

Este classificador alimenta a **política** (o estrategista escala ou sustenta a dica). A
classificação usada na **análise** é a do protocolo de avaliação (casos de teste do item mais
juiz com validação humana) e é derivada do registro estruturado, não deste módulo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Literal, TypedDict

StudentMovement = Literal[
    "PROGRESSO",
    "ESTAGNACAO",
    "REGRESSAO",
    "PEDIDO_EXPLICITO",
    "NENHUM",
]

MovementSource = Literal["codigo", "texto", "modelo", "nenhum"]


class MovementResult(TypedDict):
    movement: StudentMovement
    source: MovementSource


#: Estimador que substitui a regra textual quando o texto é quem decide. Recebe as falas do
#: estudante até à que se classifica e o estado de código vigente; devolve ``None`` quando não
#: tem estimativa para aquele turno, e aí vale a regra determinística. É por aqui que o nó do
#: grafo entra: a precedência — pedido explícito, depois compilador, depois texto — não muda.
TextClassifier = Callable[[list[str], str], "StudentMovement | None"]


#: Pedido explícito de resposta, correção ou código (H2). Exige marca imperativa/possessiva:
#: "o que está errado?" sozinho é pergunta legítima, "me fala o que está errado" é pedido.
#:
#: Os padrões de duas partes usam ``[^.!?]*`` e não ``.*``: um pedido é uma frase, não um trecho
#: qualquer do texto. ``_normalize`` colapsa toda quebra de linha em espaço, e o ``content`` que
#: chega aqui traz o **enunciado do exercício** colado à fala do estudante — um ``.*`` atravessa
#: os dois e lê o "corrija" do enunciado junto com o "meu código" do estudante como se fossem um
#: pedido. Falso positivo caro: infla o denominador de H2 e faz a política endurecer contra uma
#: exigência que nunca houve.
_EXPLICIT_REQUEST_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bme (fala|diz|fale|diga|mostra|mostre|manda|mande|de|da|entrega)\b",
        r"\b(fala|diz|diga|fale) (logo|de uma vez|pra mim|para mim)\b",
        r"\bqual (e |eh )?(a )?resposta\b",
        r"\bqual (linha|a linha)\b[^.!?]*\b(mudar|trocar|corrigir|alterar)\b",
        r"\b(manda|mande|escreve|escreva|posta|cola)\b[^.!?]*\bcodigo\b",
        r"\bcodigo (certo|corrigido|arrumado|pronto|completo)\b",
        r"\b(arruma|arrume|conserta|conserte|corrige|corrija|resolve|resolva|faz|faca)\b"
        r"[^.!?]*\b(pra mim|para mim|isso|o codigo|meu codigo)\b",
        r"\bso (me )?(diz|diga|fala|fale|mostra|mostre)\b",
        r"\bmostra (como fica|a solucao|o codigo)\b",
        r"\b(da|de|passa|passe) a resposta\b",
        r"\bqual (e |eh )?(a )?(solucao|correcao)\b",
    )
)

#: Sinais textuais de estagnação: bloqueio declarado, ausência de conteúdo novo.
_STALL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bnao (sei|entendi|entendo|consigo|faco ideia|sei nao)\b",
        r"\bsem ideia\b",
        r"\b(to|estou) (perdido|perdida|travado|travada|boiando)\b",
        r"\btravei\b",
        r"\bcontinua (igual|na mesma|o mesmo erro)\b",
        r"\bnao mudou nada\b",
        r"\bnenhuma ideia\b",
    )
)

#: Marcas de hipótese ou de observação nova. Sem nenhuma delas — e sem âncora no código — a
#: fala é "resposta fora do foco", que a regra da dissertação classifica como estagnação.
_HYPOTHESIS_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\b(acho|achei|acredito|imagino|suponho|percebi|notei|reparei|descobri|entendi)\b",
        r"\b(talvez|provavelmente|capaz)\b",
        r"\bdeve (ser|estar|dar)\b",
        # Só o causal "porque", que introduz uma razão. O conectivo sozinho — "por que",
        # "pois", "então", "logo", "ou seja" — não afirma nada: aparece igualmente em "então o
        # que eu faço agora" e em "pois é, complicado isso", que são bloqueio textual. Contá-lo
        # como hipótese reproduz o defeito que esta regra corrige: o tutor deixa de escalar sob
        # bloqueio. As hipóteses reais ficam cobertas pelos demais padrões e pela âncora.
        r"\bporque\b",
        r"\b(testei|rodei|tentei|mudei|troquei|coloquei|apaguei|corrigi|executei|rodou)\b",
        # Negado, o verbo de desfecho é queixa, não observação: "nao funciona" não diz o que
        # aconteceu. Quando há ação junto ("testei e nao deu certo"), o padrão de ação decide.
        r"(?<!\bnao )\b(deu|da|escreveu|imprimiu|apareceu|compilou|funciona|funcionou|parou)\b",
        r"\b(devia|deveria|esperava|esperado)\b",
        r"\b(faltava|falta|faltou|sobra|sobrando|sem o|sem a)\b",
        r"\bvi que\b",
        r"\bo (problema|erro|defeito) (e|esta|era)\b",
    )
)

#: Palavras que são construto do Portugol e, ao mesmo tempo, palavra corrente do português:
#: não servem de âncora, sob pena de qualquer frase parecer ancorada no código.
_NEUTRAS = frozenset(
    {"para", "entao", "senao", "faca", "pare", "tipo", "nao", "com", "por", "que"}
)

#: Símbolo do código que sirva de âncora: identificador de três letras ou mais, ou número.
_SIMBOLO = re.compile(r"[a-z_]\w{2,}|\d+")

#: Afirmação de que o programa está correto. Sem edição de código, é a ``REGRESSAO`` textual
#: da dissertação na única forma que um classificador determinístico alcança.
_AFIRMA_CORRETO: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"(?<!se )\b(esta|ta|e|era|fica|parece) (certo|correto|certinho|corretinho)\b",
        r"\bnao (tem|ha|vejo) (nada de |nenhum )?(errado|erro|problema)\b",
        r"(?<!se )\b(esta|ta) (funcionando|funcionado) (certo|bem|direito)\b",
        r"\btudo certo\b",
    )
)

#: Marcas de dúvida: com elas a frase é pergunta ou hesitação, não afirmação.
_DUVIDA = re.compile(r"\bsera\b|\bcomo eu sei\b|\bnao sei\b|\bsera que\b")

#: Abaixo disto a mensagem não carrega conteúdo novo suficiente para contar como progresso.
_MIN_SUBSTANTIVE_CHARS = 12

#: Sobreposição de palavras a partir da qual a fala é repetição do que o estudante já disse.
_LIMIAR_REPETICAO = 0.8


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def _user_turns(history: list[dict]) -> list[str]:
    return [
        str(item.get("content", ""))
        for item in history
        if isinstance(item, dict) and item.get("role") == "user"
    ]


def is_explicit_request(text: str) -> bool:
    """Pedido explícito de resposta, correção ou código (condição de H2)."""
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in _EXPLICIT_REQUEST_PATTERNS)


def _palavras(normalized: str) -> set[str]:
    return set(re.findall(r"[a-z_0-9]+", normalized))


def _repete(normalized: str, anteriores: list[str]) -> bool:
    """Repetição da própria fala, literal ou quase: a mesma coisa dita com outras palavras."""
    atual = _palavras(normalized)
    for previous in anteriores:
        anterior_norm = _normalize(previous)
        if anterior_norm == normalized:
            return True
        antes = _palavras(anterior_norm)
        if not atual or not antes:
            continue
        uniao = atual | antes
        if len(atual & antes) / len(uniao) >= _LIMIAR_REPETICAO:
            return True
    return False


def _ancorado_no_codigo(normalized: str, code: str) -> bool:
    """A fala cita símbolo do programa (variável, número) ou uma linha: está no foco da tarefa."""
    if re.search(r"\blinha \d+\b", normalized):
        return True
    do_codigo = {s for s in _SIMBOLO.findall(_normalize(code))} - _NEUTRAS
    da_fala = {s for s in _SIMBOLO.findall(normalized)} - _NEUTRAS
    return bool(do_codigo & da_fala)


def afirma_que_esta_correto(text: str) -> bool:
    """A fala **afirma** que o programa está certo (não pergunta, não hesita).

    Decide-se por frase: "Escreveu Reprovado. Mas acho que está certo" afirma; "Será que está
    certo?" e "não sei se está certo" não.
    """
    normalized = _normalize(text)
    for frase in re.split(r"[.!?]+", normalized):
        frase = frase.strip()
        if not frase or _DUVIDA.search(frase):
            continue
        if not any(pattern.search(frase) for pattern in _AFIRMA_CORRETO):
            continue
        inicio = normalized.find(frase)
        fim = inicio + len(frase)
        if inicio >= 0 and normalized[fim : fim + 1] == "?":
            continue
        return True
    return False


def _classify_by_text(user_turns: list[str], code: str) -> StudentMovement:
    """
    Sem edição de código, decide o texto do último turno.

    ``PROGRESSO`` é hipótese ou observação nova sobre a tarefa; "não sei", a repetição e a
    resposta fora do foco são ``ESTAGNACAO``. O comprimento da fala, sozinho, não é progresso.
    """
    last = user_turns[-1]
    normalized = _normalize(last)
    if not normalized:
        return "ESTAGNACAO"
    if any(pattern.search(normalized) for pattern in _STALL_PATTERNS):
        return "ESTAGNACAO"
    if _repete(normalized, user_turns[:-1]):
        return "ESTAGNACAO"
    if len(normalized) < _MIN_SUBSTANTIVE_CHARS:
        return "ESTAGNACAO"
    if any(pattern.search(normalized) for pattern in _HYPOTHESIS_PATTERNS):
        # Hipótese ou observação nova. Se ela está *errada*, a dissertação chama de regressão,
        # mas julgar a correção da hipótese não cabe a um classificador determinístico: isso
        # fica com a classificação da medida, e a divergência é reportada.
        return "PROGRESSO"
    if _ancorado_no_codigo(normalized, code):
        return "PROGRESSO"
    # Fala longa, sem hipótese e fora do foco da tarefa: estagnação, como manda a regra.
    return "ESTAGNACAO"


def _classify_by_code(previous_errors: list[str], errors: list[str]) -> StudentMovement | None:
    before = [e for e in previous_errors if str(e).strip()]
    after = [e for e in errors if str(e).strip()]
    if before and not after:
        return "PROGRESSO"
    if after and not before:
        return "REGRESSAO"
    if len(after) < len(before):
        return "PROGRESSO"
    if len(after) > len(before):
        return "REGRESSAO"
    if before and set(map(str, before)) == set(map(str, after)):
        # Editou, e o compilador diz exatamente o mesmo: nada mudou.
        return "ESTAGNACAO"
    # Mesmo número de erros com conteúdo distinto, ou erro puramente lógico (sem erro de
    # compilação nos dois estados): o compilador não decide; devolve ao texto.
    return None


def classify_movement(
    *,
    code: str,
    history: list[dict],
    errors: list[str] | None = None,
    previous_code: str | None = None,
    previous_errors: list[str] | None = None,
    classificador_textual: TextClassifier | None = None,
) -> MovementResult:
    """
    Classifica o último turno do estudante.

    Precedência: pedido explícito > regra do código (quando houve edição e o compilador
    decide) > sinal do texto. No turno de abertura não há movimento a classificar — não existe
    turno anterior do estudante contra o qual comparar —, e o resultado é ``NENHUM``.

    ``classificador_textual`` substitui **só** o último degrau, o do texto. O pedido explícito e
    a regra do compilador continuam determinísticos: o primeiro é a condição de H2 e o segundo é
    evidência objetiva, e nenhum dos dois melhora por ser estimado.
    """
    user_turns = _user_turns(history)
    if not user_turns:
        return {"movement": "NENHUM", "source": "nenhum"}

    if is_explicit_request(user_turns[-1]):
        # O pedido explícito prevalece sobre as demais categorias, inclusive na abertura:
        # é o sinal de que a política precisa para não passar do nível conceitual.
        return {"movement": "PEDIDO_EXPLICITO", "source": "texto"}

    if len(user_turns) == 1 and previous_code is None:
        return {"movement": "NENHUM", "source": "nenhum"}

    houve_edicao = previous_code is not None and previous_code != code
    if houve_edicao:
        by_code = _classify_by_code(previous_errors or [], errors or [])
        if by_code is not None:
            return {"movement": by_code, "source": "codigo"}

    # Só sem edição: com edição, "agora está certo" costuma ser relato de correção, e quem
    # decide é o código. É por isso que esta regra não pode viver dentro de ``_classify_by_text``.
    if not houve_edicao and afirma_que_esta_correto(user_turns[-1]):
        return {"movement": "REGRESSAO", "source": "texto"}

    if classificador_textual is not None:
        estimado = classificador_textual(user_turns, code)
        if estimado is not None:
            return {"movement": estimado, "source": "modelo"}
    return {"movement": _classify_by_text(user_turns, code), "source": "texto"}


#: Movimentos que contam como bloqueio e por isso acumulam. ``PROGRESSO`` zera o contador;
#: ``PEDIDO_EXPLICITO`` e ``NENHUM`` transportam-no sem o alterar.
MOVIMENTOS_DE_BLOQUEIO: tuple[StudentMovement, ...] = ("ESTAGNACAO", "REGRESSAO")

StreakSource = Literal["historico", "turno", "nenhum"]


class StreakResult(TypedDict):
    streak: int
    source: StreakSource


def _estado_do_turno(turno: dict) -> tuple[str, list[str]] | None:
    """Estado do código e erros que o cliente anexou ao turno do estudante, se anexou."""
    codigo = turno.get("code")
    if not isinstance(codigo, str):
        return None
    erros = turno.get("errors")
    lista = [str(e) for e in erros] if isinstance(erros, list) else []
    return codigo, lista


def stagnation_streak(
    history: list[dict],
    *,
    current_movement: StudentMovement,
    classificador_textual: TextClassifier | None = None,
) -> StreakResult:
    """
    Turnos de bloqueio acumulados desde o último progresso — a variável independente de H1.

    A definição é a da dissertação: incrementa em ``ESTAGNACAO`` e ``REGRESSAO``, zera em
    ``PROGRESSO``, e o pedido explícito transporta o contador sem o alterar. O contador é
    derivado aqui, e não recebido pronto: cada turno do estudante em ``history`` é
    reclassificado por :func:`classify_movement` sobre o estado de código que o acompanha. É
    por isso que o artefato consome a própria variável, em vez de o cliente lha entregar.

    Sem os estados por turno o histórico não é reclassificável, e o contador degrada para o que
    o pedido deixa ver: o turno corrente. ``source`` distingue os dois casos, e a distinção
    entra na telemetria, porque um contador degradado não sustenta leitura de contingência.
    """
    indices = [
        i for i, item in enumerate(history)
        if isinstance(item, dict) and item.get("role") == "user"
    ]
    if not indices:
        return {"streak": 0, "source": "nenhum"}

    estados = [_estado_do_turno(history[i]) for i in indices]
    if any(estado is None for estado in estados):
        # Estado parcial conta como ausente: um contador montado sobre parte dos turnos erra
        # em silêncio, e errar em silêncio é pior do que degradar declaradamente.
        return {
            "streak": 1 if current_movement in MOVIMENTOS_DE_BLOQUEIO else 0,
            "source": "turno",
        }

    streak = 0
    for posicao, indice in enumerate(indices):
        anterior = estados[posicao - 1] if posicao else None
        codigo, erros = estados[posicao]
        movimento = classify_movement(
            code=codigo,
            history=history[: indice + 1],
            errors=erros,
            previous_code=anterior[0] if anterior else None,
            previous_errors=anterior[1] if anterior else None,
            classificador_textual=classificador_textual,
        )["movement"]
        if movimento in MOVIMENTOS_DE_BLOQUEIO:
            streak += 1
        elif movimento == "PROGRESSO":
            streak = 0
    return {"streak": streak, "source": "historico"}


def turnos_que_o_texto_decide(history: list[dict]) -> list[int]:
    """Posições dos turnos do estudante (0-based) em que o degrau do texto é quem decide.

    É a lista que o estimador do nó precisa de rotular. Sai de correr a **própria** precedência
    com uma sonda no lugar da regra textual, em vez de a reimplementar: mudar
    :func:`classify_movement` muda esta função junto, sem ninguém se lembrar dela.

    Vazia quando o histórico não é reclassificável — sem o estado de código por turno não há o
    que percorrer, e o contador degrada como sempre degradou.
    """
    vistos: list[int] = []

    def _sonda(user_turns: list[str], code: str) -> StudentMovement:
        vistos.append(len(user_turns) - 1)
        return "ESTAGNACAO"

    stagnation_streak(history, current_movement="NENHUM", classificador_textual=_sonda)
    return vistos
