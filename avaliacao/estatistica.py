"""Estatística da bancada, em Python puro: proporções com Wilson e concordância por kappa.

O plano analítico (Subseção 4.3.5) usa intervalo de Wilson a 95% para H2 e as taxas de
contingência, e kappa de Cohen (nominais) e kappa ponderado linear (ordinais) para a validação
do juiz contra a codificação humana, com aceitação em 0,60 (Landis e Koch, 1977). Um κ
indefinido é ``nan`` e não satisfaz o critério: quem decide o que fazer com ele é quem lê.

O modelo ordinal misto de H1 não está aqui: exige statsmodels ou R e roda sobre o CSV exportado
por ``analisar`` (``h1_turnos.csv``), fora deste pacote, que é deliberadamente sem dependências.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Proporcao:
    sucessos: int
    total: int
    estimativa: float
    inferior: float
    superior: float

    def como_texto(self, casas: int = 3) -> str:
        if not self.total:
            return "—"
        return (
            f"{self.estimativa:.{casas}f} "
            f"[{self.inferior:.{casas}f}; {self.superior:.{casas}f}] (n={self.total})"
        )


def wilson(sucessos: int, total: int, z: float = Z_95) -> Proporcao:
    """Intervalo de Wilson a 95% — o usado para H2 e para as taxas de contingência."""
    if total <= 0:
        return Proporcao(sucessos, 0, float("nan"), float("nan"), float("nan"))
    p = sucessos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margem = (z / denominador) * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return Proporcao(sucessos, total, p, max(0.0, centro - margem), min(1.0, centro + margem))


@dataclass(frozen=True)
class Diferenca:
    """Diferença entre duas proporções independentes, com intervalo a 95%."""

    estimativa: float
    inferior: float
    superior: float
    total_a: int
    total_b: int

    def como_texto(self, casas: int = 3) -> str:
        if not self.total_a or not self.total_b:
            return "—"
        return (
            f"{self.estimativa:+.{casas}f} "
            f"[{self.inferior:+.{casas}f}; {self.superior:+.{casas}f}]"
        )


def diferenca_wilson(a: Proporcao, b: Proporcao) -> Diferenca:
    """Diferença ``a - b`` pelo método de Newcombe (1998), que compõe os dois Wilson.

    Sem isto, P(revelação | pedido) − P(revelação | outros) sai como dois números soltos e o
    texto não pode dizer se a diferença é distinguível de zero.
    """
    if not a.total or not b.total:
        return Diferenca(float("nan"), float("nan"), float("nan"), a.total, b.total)
    delta = a.estimativa - b.estimativa
    inferior = delta - math.sqrt((a.estimativa - a.inferior) ** 2 + (b.superior - b.estimativa) ** 2)
    superior = delta + math.sqrt((a.superior - a.estimativa) ** 2 + (b.estimativa - b.inferior) ** 2)
    return Diferenca(delta, max(-1.0, inferior), min(1.0, superior), a.total, b.total)


def media(valores: Iterable[float]) -> float:
    itens = [v for v in valores if v is not None]
    return sum(itens) / len(itens) if itens else float("nan")


def desvio_padrao(valores: Iterable[float]) -> float:
    itens = [v for v in valores if v is not None]
    if len(itens) < 2:
        return 0.0
    m = sum(itens) / len(itens)
    return math.sqrt(sum((v - m) ** 2 for v in itens) / (len(itens) - 1))


def mediana(valores: Iterable[float]) -> float:
    itens = sorted(v for v in valores if v is not None)
    if not itens:
        return float("nan")
    meio = len(itens) // 2
    if len(itens) % 2:
        return float(itens[meio])
    return (itens[meio - 1] + itens[meio]) / 2


def kappa_cohen(a: Sequence, b: Sequence) -> float:
    """Kappa de Cohen para variáveis nominais (movimento, falhas, ancoragem)."""
    return _kappa(a, b, ponderado=False)


def kappa_ponderado(a: Sequence, b: Sequence, *, escala: Sequence | None = None) -> float:
    """Kappa ponderado linear para as ordinais (diretividade 0–3, fidelidade 1–3).

    A ``escala`` é a do instrumento, não a da amostra: se um nível não aparecer na subamostra,
    o peso linear ``1 - |i-j|/(k-1)`` muda de tamanho e o κ deixa de ser comparável entre
    variáveis e entre execuções. Passe sempre a escala declarada da variável.
    """
    return _kappa(a, b, ponderado=True, escala=escala)


def _kappa(a: Sequence, b: Sequence, *, ponderado: bool, escala: Sequence | None = None) -> float:
    """κ, ou ``nan`` quando ele é **indefinido** — não 1,0.

    Com uma só categoria observada (ou com a concordância esperada em 1) não há acaso a
    descontar e o κ não existe. Devolver 1,0 aí faria uma amostra degenerada — p. ex. todas as
    codificações de ``prematura`` iguais a ``False`` — passar no critério de aceitação de 0,60.
    """
    pares = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if escala is not None:
        permitidos = list(escala)
        pares = [(x, y) for x, y in pares if x in permitidos and y in permitidos]
        categorias = permitidos
    else:
        categorias = sorted({valor for par in pares for valor in par}, key=_ordenavel)
    if not pares:
        return float("nan")
    indice = {categoria: i for i, categoria in enumerate(categorias)}
    n = len(pares)
    k = len(categorias)
    if k < 2:
        return float("nan")

    observado = [[0.0] * k for _ in range(k)]
    for x, y in pares:
        observado[indice[x]][indice[y]] += 1 / n
    marginais_a = [sum(linha) for linha in observado]
    marginais_b = [sum(observado[i][j] for i in range(k)) for j in range(k)]

    def peso(i: int, j: int) -> float:
        if not ponderado:
            return 1.0 if i == j else 0.0
        return 1 - abs(i - j) / (k - 1)

    po = sum(peso(i, j) * observado[i][j] for i in range(k) for j in range(k))
    pe = sum(peso(i, j) * marginais_a[i] * marginais_b[j] for i in range(k) for j in range(k))
    if math.isclose(pe, 1.0):
        return float("nan")
    return (po - pe) / (1 - pe)


def _ordenavel(valor) -> tuple[int, float, str]:
    if isinstance(valor, bool):
        return (0, float(valor), "")
    if isinstance(valor, (int, float)):
        return (0, float(valor), "")
    return (1, 0.0, str(valor))


@dataclass(frozen=True)
class Intervalo:
    """Intervalo a 95% de um κ, por bootstrap; ``reamostras_validas`` conta as que deram κ definido."""

    inferior: float
    superior: float
    reamostras_validas: int
    reamostras: int

    def como_texto(self, casas: int = 3) -> str:
        if self.reamostras_validas == 0:
            return "[—; —]"
        return f"[{self.inferior:.{casas}f}; {self.superior:.{casas}f}]"


def intervalo_bootstrap(
    a: Sequence,
    b: Sequence,
    funcao,
    *,
    reamostras: int = 2000,
    semente: int = 20260912,
) -> Intervalo:
    """IC percentílico a 95% de uma estatística de concordância, por bootstrap sobre os pares.

    Reamostram-se os pares ``(a_i, b_i)`` com reposição, ``reamostras`` vezes, e recalcula-se
    ``funcao`` (um dos kappas acima) em cada reamostra; o intervalo são os percentis 2,5 e 97,5
    das estimativas **definidas** — uma reamostra que caia numa só categoria dá ``nan`` e é
    descartada, e o número descartado fica visível em ``reamostras_validas``. A semente é fixa
    para o intervalo ser o mesmo em cada corrida do script: um IC que muda entre execuções sem
    os dados mudarem não é reprodutível.

    É não paramétrico de propósito: a variância assintótica do κ ponderado (Fleiss, Cohen e
    Everitt, 1969) exige marginais bem povoadas, e as falhas raras da rubrica não as têm.
    """
    import random

    pares = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pares) < 2:
        return Intervalo(float("nan"), float("nan"), 0, reamostras)
    gerador = random.Random(semente)
    n = len(pares)
    estimativas: list[float] = []
    for _ in range(reamostras):
        indices = [gerador.randrange(n) for _ in range(n)]
        valor = funcao([pares[i][0] for i in indices], [pares[i][1] for i in indices])
        if valor == valor:  # não é nan
            estimativas.append(valor)
    if not estimativas:
        return Intervalo(float("nan"), float("nan"), 0, reamostras)
    estimativas.sort()
    return Intervalo(
        _percentil(estimativas, 2.5),
        _percentil(estimativas, 97.5),
        len(estimativas),
        reamostras,
    )


def _percentil(ordenados: Sequence[float], p: float) -> float:
    """Percentil por interpolação linear sobre uma sequência já ordenada."""
    if len(ordenados) == 1:
        return ordenados[0]
    posicao = (len(ordenados) - 1) * p / 100
    baixo = math.floor(posicao)
    alto = min(baixo + 1, len(ordenados) - 1)
    fracao = posicao - baixo
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * fracao
