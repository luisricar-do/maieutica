# Rubrica revista — NÃO APLICADA aos resultados do Capítulo 4

> **Estado deste artefacto.** Esta é a revisão da rubrica de codificação proposta depois da
> validação humana da execução `cap4`, e **não foi aplicada** aos 2 020 juízos reportados. O
> prompt em vigor continua a ser `juiz.md`, cujo *hash* está publicado e amarra o artefacto aos
> números da dissertação. Aplicar esta revisão obriga a rejulgar a execução inteira e a
> recodificar a amostra humana; fica como revisão documentada, para replicação.
>
> **O que muda, e porquê.** Duas correções, ambas motivadas por evidência da subamostra de 210
> turnos codificados à mão:
>
> 1. **Fidelidade deixa de ser forçada pela diretividade.** Na rubrica em vigor, o critério (1)
>    da fidelidade — *"orienta sem entregar, não revela a correção"* — é, palavra por palavra, a
>    definição de diretividade 3. O resultado é dedutivo e não empírico: 81 de 81 turnos de nível
>    3 na codificação humana, e 70 de 71 na do juiz, receberam fidelidade 1. Medido fora desse
>    bloco, o κ humano×juiz da fidelidade cai de 0,70 para 0,40 — ou seja, a confiabilidade
>    aparente vinha quase toda de um acordo que a rubrica impunha.
>    O erro de fundo é de categoria: tratar **ausência** de andaime como o **pior** andaime. Um
>    turno que entrega a correção não é um andaime mau, é um turno sem andaime a graduar.
> 2. **Entra uma quinta falha, `incorreta`.** Em 15 dos 210 turnos, a intervenção afirma algo
>    falso sobre o programa, sobre a linguagem ou sobre o enunciado, ou refere elemento que não
>    existe no estado atual. Nenhuma das quatro falhas cobre isso, e o juiz automático empurrava
>    o caso para `irrelevante` — o que explica o κ de 0,386 nessa variável, a mais baixa de
>    todas. O caso mais nítido é um turno que confunde Fahrenheit com Celsius e recebeu do juiz
>    fidelidade 3 e nenhuma falha.

## 1. Diretividade do turno do tutor (0 a 3)

Inalterada face a `juiz.md`. Mede quanto da solução a intervenção entrega; o turno recebe **o
nível mais alto que qualquer das suas frases atinge**.

| Nível | Nome | Definição operacional |
|---|---|---|
| 0 | Aberta | Pergunta ou observação que não aponta região do código nem natureza do erro. |
| 1 | Focada | Dirige a atenção à linha, variável ou construto do defeito, sem dizer qual é o problema. |
| 2 | Conceitual | Nomeia a natureza do erro ou o conceito envolvido, sem a correção concreta. |
| 3 | Revelação | Entrega a correção concreta, em código ou em instrução de edição inequívoca. |

Regras de desempate inalteradas.

## 2. Movimento do estudante

Inalterado. Acrescenta-se uma **nota de codificação**, motivada pela subamostra: `REGRESSAO` e
`NENHUM` são categorias reais e pouco usadas — nas anotações-ouro dos 180 turnos com ouro
disponível ocorrem 6 e 13 vezes, e o codificador humano não usou nenhuma das duas, colapsando-as
em `ESTAGNACAO` e `PROGRESSO`. Antes de codificar `ESTAGNACAO`, verifique se o estudante de facto
falou; antes de `PROGRESSO`, se ele não está a abandonar um acerto anterior.

## 3. Fidelidade do andaime (não aplicável, 1 a 3)

**Só se aplica a turnos de diretividade 0, 1 ou 2.** Num turno de diretividade 3 não há andaime a
graduar: registe `nao_aplicavel`. Não é uma fidelidade baixa — é a ausência do objeto que a escala
mede, e confundir as duas coisas era o defeito da versão anterior.

Onde se aplica, avalie **quatro** critérios (o antigo critério (1) sai, por ser a diretividade):

1. **Ancorada no estado do programa** — pode ser respondida pela inspeção do próprio código, de
   uma variável, de uma condição ou do fluxo de execução.
2. **Elicia verificação ou hipótese** — solicita ao estudante que preveja, verifique ou articule
   a causa.
3. **Um passo de cada vez** — avança a investigação por um único passo tratável.
4. **Pertinente, nova e oportuna** — relaciona-se ao erro em foco, não repete pista já dada nem
   antecipa a edição antes de o estudante formular uma hipótese.

| Nível | Critério |
|---|---|
| 1 | Falha em dois ou mais dos quatro. |
| 2 | Satisfaz todos menos um. |
| 3 | Satisfaz os quatro. |

## 4. Ancoragem

Inalterada: `sim`, `nao`, `alvo_errado`.

**Ancoragem e correção são independentes.** `alvo_errado` diz que o turno aponta para linha,
variável ou construto que não são os do defeito. A falha `incorreta` (§5) diz que o turno afirma
algo falso. Um turno pode ser as duas coisas — apontar ao sítio errado *e* dizer uma falsidade — e
nesse caso recebe as duas marcas. Na subamostra, os 6 turnos com `alvo_errado` eram todos também
`incorreta`, mas 9 outros eram `incorreta` estando ancorados no alvo **certo**.

## 5. Falhas (binárias, múltiplas permitidas)

| Dimensão | Critério operacional |
|---|---|
| irrelevante | A intervenção desvia do erro, da tarefa ou do código em foco. |
| repetida | Repergunta o que o estudante já respondeu ou repete a mesma pista sem progresso. |
| excessivamente_direta | Antecipa a correção, indica mudança concreta no código ou reduz o desafio cognitivo. |
| prematura | Orienta edição antes de o estudante articular hipótese sobre a causa. |
| **incorreta** | **A intervenção afirma algo falso sobre o programa, sobre a linguagem ou sobre o enunciado, ou refere elemento que não existe no estado atual do código ou da conversa.** |

Casos que `incorreta` cobre, todos observados na subamostra: correção concreta que não corrige
(propor mover o incremento para antes da multiplicação, que produziria saída errada); valor
trocado (perguntar o que acontece "quando c é igual a 32" num conversor em que 32 é a fronteira
em Fahrenheit, não em Celsius); código entregue com sintaxe que a linguagem não aceita; citar
"trecho destacado", mensagem do compilador ou função que não existem no prefixo; afirmar que está
errado o que o enunciado declara correto.

Cobrir `incorreta` **não** é julgar a elegância nem a completude: uma pergunta parcial, vaga ou
pouco útil, mas verdadeira, não é incorreta.

## 6. Formato da resposta

```json
{
  "diretividade": 0,
  "movimento_estudante": "ESTAGNACAO",
  "fidelidade": 3,
  "falhas": {
    "irrelevante": false,
    "repetida": false,
    "excessivamente_direta": false,
    "prematura": false,
    "incorreta": false
  },
  "ancorado": "sim",
  "justificativa": "uma frase"
}
```

`fidelidade` aceita `1`, `2`, `3` ou a cadeia `"nao_aplicavel"` quando `diretividade` é 3.
