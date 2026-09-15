# Ciclos de avaliação da política de intervenção

Qual corrida responde ao Capítulo 5, e por quê. O registro existe porque a distinção entre
avaliação **formativa** (do ciclo de design) e **somativa** (a que o capítulo reporta) só tem
valor se for declarada **antes** de a corrida seguinte existir. Declarada depois, é escolha de
resultado.

## Ciclo 1 — `execucoes/cap4` — FORMATIVA

Corrida completa das três condições sobre os 25 itens, 2.020 vereditos, juiz
`gemini-3.1-pro-preview`, validação humana com κ = 0,791 (diretividade) e κ = 0,844 (movimento).

Resultado de H1: **não sustentada** pelo critério declarado — efeito do acúmulo de estagnação
+0,190 (EP 0,652; IC 95% [−1,088; 1,468]; p = 0,771), sobre 141 turnos bloqueados. H2
sustentada: 0,010 [0,002; 0,054].

A apuração levou à leitura do código da política, e essa leitura achou um defeito de
implementação: **o estrategista escalava por `debug_user_turns`**, a contagem total de turnos do
estudante na sessão, e não pela **estagnação acumulada desde o último progresso**, que é a
variável independente que a dissertação declara para H1. As duas divergem sempre que há
progresso no meio do episódio: a primeira nunca reinicia, a segunda reinicia. O artefato não
tinha contador de estagnação em lugar nenhum do código — logo o coeficiente nulo mede uma
variável que a política nunca consumiu.

Por isso este ciclo é **formativo**: avaliação que alimenta a iteração de design, no sentido do
ciclo de design da DSR. Ele **não desaparece** da dissertação — é reportado como a avaliação que
revelou o defeito e motivou a correção, e é o que dá lastro à contribuição metodológica de que o
protocolo mede a política em vez de a asseverar.

## Ciclo 2 — após a correção — SOMATIVA

É a corrida que o Capítulo 5 reporta. Compromissos assumidos **antes** de ela existir:

1. **O resultado vai para o capítulo seja ele qual for.** Se H1 voltar a não se sustentar, é
   essa a resposta reportada. Não há terceiro ciclo escolhido por resultado.
2. **O critério de sustentação não muda**: efeito do acúmulo de estagnação positivo ao nível de
   5% e efeito do progresso não positivo (Subseção 4.3 da dissertação). Sem mudança de nível,
   sem teste unilateral, sem troca do termo principal pelo da regressão.
3. **O limiar de escalonamento do artefato não muda**: a política escala a partir de 4 turnos
   bloqueados acumulados, como o Capítulo 1 descreve ("por volta do quarto ou quinto turno, se o
   bloqueio persistir"). Baixá-lo para o artefato passar no próprio teste seria desenhar a
   política a partir da hipótese.
4. **A estrutura aleatória e as sensibilidades são as do ciclo 1**, pelos mesmos scripts.

### Limitação conhecida, declarada antes da corrida

O corpus de prefixos quase não alcança a região em que a política escala. Contagem sobre os
**135 prefixos elegíveis a H1** (ouro, k ≥ 2, sem pedido explícito), com o contador já corrigido:

| acumulado que o artefato vê | prefixos | o que a política manda fazer |
| --- | --- | --- |
| 0 | 80 | não escalar (progresso) |
| 1–3 | 53 | sustentar o nível, não escalar |
| ≥ 4 | 2 | escalar um degrau |

A regra corrigida só pode disparar em **2 dos 135**. Corrigir o contador era necessário — o
artefato consumia a variável errada —, mas não é suficiente para H1 se sustentar em bancada: a
variável independente não visita a faixa onde a política responde. Fica registrado aqui, antes
do resultado, para que não seja lido depois como justificação construída sobre ele.

O remédio para isso é de instrumento, não de política: prefixos de bloqueio mais fundos, que
cheguem a 5–6 turnos acumulados. Se for feito, entra como ciclo próprio, com o n e o critério
fixados antes de correr.

## Correção aplicada entre os ciclos

- `agents/movement.py`: `stagnation_streak` deriva o acumulado reclassificando cada turno do
  histórico, com a mesma definição da apuração (`avaliacao/itens.py`) — incrementa em
  `ESTAGNACAO`/`REGRESSAO`, zera em `PROGRESSO`, e o pedido explícito transporta sem alterar.
- `agents/strategist.py`: a regra de contingência e o ritmo do `hint_level` passam a depender do
  acumulado, e o prompt declara que a contagem de turnos **não** é o gatilho.
- O contador é **derivado pelo serviço**, não recebido pronto do cliente: o pedido traz o estado
  de código por turno e o serviço reclassifica. É o que mantém a variável independente fora das
  mãos de quem é avaliado.
- Concordância com a anotação do harness sobre o banco: 189 de 260 prefixos. As 71 divergências
  são a assimetria já declarada na metodologia — o artefato classifica sem executar os casos de
  teste, a medida os executa.
