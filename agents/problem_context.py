"""Enunciado do exercício como contexto do pedido — nunca como fala do estudante.

Em sala a IDE não envia enunciado: o tutor infere a tarefa do código. A bancada precisa dele,
porque o protocolo de Al-Hossami dá a descrição do problema a quem orienta, e os turnos de
referência foram escritos por humanos que a tinham.

Até aqui a bancada resolvia isso colando o enunciado ao primeiro ``content`` do estudante. O
preço era alto e invisível: toda leitura textual do turno passava a ler o enunciado como se
fosse fala do estudante. ``_normalize`` colapsa a quebra de linha entre os dois, e daí o
"corrija" do enunciado casava com o "meu código" do estudante num único pedido explícito. O
mesmo vale para os padrões de estagnação, os de hipótese e o teste de repetição por sobreposição
de palavras, que em k=1 ficava diluído pelo enunciado inteiro.

O enunciado passa a viajar em campo próprio (``problemStatement``) e a entrar na conversa como
mensagem de contexto antes do histórico — a mesma posição que o molde de código já ocupa nas
condições B e C, e o que ``hashes-congelados.md`` sempre descreveu: "o molde é a primeira
mensagem, nunca conteúdo anexado à fala do estudante".
"""

from __future__ import annotations

import hashlib

#: Teto de tamanho: enunciado é enunciado, não anexo. Acima disto trunca-se.
LIMITE_ENUNCIADO = 4000

PROBLEM_TEMPLATE = """\
Exercise statement the student is working on:
{problem_statement}"""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Identidade do molde na corrida, ao lado dos prompts e do molde de contexto.
PROBLEM_SHA256: str = _sha256(PROBLEM_TEMPLATE)


def parse_problem_statement(raw: object) -> str:
    """Campo opcional do payload; vazio quando ausente ou malformado."""
    if not isinstance(raw, str):
        return ""
    return raw.strip()[:LIMITE_ENUNCIADO]


def build_problem_content(problem_statement: str) -> str:
    """Conteúdo da mensagem de contexto do enunciado. Vazio não gera mensagem."""
    return PROBLEM_TEMPLATE.format(problem_statement=problem_statement.strip())
