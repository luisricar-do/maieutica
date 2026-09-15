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

### O que o ciclo 1 tinha como detectar

`analise_tese/poder_h1.R` simula a precisão do efeito do acúmulo sobre a estrutura ajustada — os
limiares e as variâncias de item (1,01) e de prefixo (13,40) do ajuste que o critério de H1 lê —
e reproduz o erro-padrão observado: 0,617 simulado contra 0,652 medido. É essa concordância que
autoriza ler o resto.

O acumulado é covariável de **nível-prefixo**: vale um valor só por prefixo. Os 141 turnos
bloqueados são, para efeito de estimação, **47 prefixos**, e as três execuções de cada um não
compram precisão para este efeito — compram para a variabilidade entre corridas, que é outra
pergunta. Com variância de prefixo 13,40, o erro-padrão vai como
`sqrt(13,40 / (n_prefixos × Var(acumulado)))`, e é por isso que aumentar execuções não move nada.

Daí o número que reenquadra o ciclo 1. Com 47 prefixos bloqueados e variância do acumulado 2,15,
o desenho tem **16% de poder** para um efeito de 0,6 logito por turno acumulado, e precisaria de
**1,73** — razão de chances 5,6 a cada turno de bloqueio — para chegar a 80%. O ciclo 1 não tinha
como detectar um efeito de tamanho plausível, e o `p = 0,771` mede sobretudo isso.

Isto não converte não sustentação em sustentação: um intervalo largo é um intervalo largo, não um
efeito escondido. Mas muda o que a dissertação pode afirmar — de "o artefato não escala com a
estagnação acumulada" para "este desenho não distingue as duas hipóteses", que é a afirmação que
os dados sustentam. O ciclo 1 não foi só formativo quanto ao artefato; foi formativo quanto ao
instrumento.

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

### Extensão do banco, fixada antes de correr

O remédio é de instrumento, não de política, e entra **antes** da corrida somativa, não como
ciclo à parte: **20 itens novos com bloqueio de profundidade 6**.

Cada item novo tem oito turnos do estudante — abertura em `NENHUM`, seis turnos bloqueados
(`ESTAGNACAO` ou `REGRESSAO`) **sem edição de código**, e um `PROGRESSO` final — e oito turnos
de tutor de referência. Rende oito prefixos ouro, seis deles com acumulado 1 a 6, mais os quatro
de pressão que a expansão gera. O molde é `banco/tese_06_contagem.json`, que já tem essa forma em
profundidade 4.

O número sai da simulação (`analise_tese/poder_h1.R`), não de conveniência. Com 20 itens o
erro-padrão do efeito do acúmulo cai de 0,617 para 0,216: 79% de poder para um efeito de 0,6, e
detectável a 80% qualquer efeito a partir de 0,60. Com 10 itens seriam 51%; com 35, 92%.

A profundidade não se troca por quantidade. Vinte itens de profundidade 4 dão erro-padrão 0,364,
**pior** que dez de profundidade 6 (0,304), apesar de mais prefixos: o que conta é a dispersão do
acumulado entre prefixos, e `Var(1..4) = 1,25` contra `Var(1..6) = 2,92`.

Os itens novos correm em todas as condições, como os 25 existentes, para o banco continuar
uniforme e alimentar também as descritivas e a ablação. A corrida somativa passa de 1 860 para
cerca de 3 540 chamadas.

### O que a extensão não resolve

Três coisas ficam declaradas antes, para não serem lidas depois como justificação.

Os 20 itens são todos `origem: tese`, redigidos pelo autor. A sensibilidade por origem, que já
está no plano analítico, passa a ser o teste de dependência do corpus construído: se H1 se
sustentar só nos itens `tese` e não nos traduzidos, isso é resultado a reportar. No ciclo 1 o
coeficiente do acúmulo já diverge por origem — −0,975 em `tese` contra +0,579 em `al_hossami_v2`
—, o que torna a checagem obrigatória e não decorativa.

As componentes de variância que dimensionaram a extensão vieram do artefato com o contador
partido. Assume-se que a heterogeneidade entre prefixos persiste na versão corrigida. É
suposição declarada, não medida.

E poder não faz o efeito existir. Em bancada o turno anterior do tutor é humano e fica em 0,277
de diretividade após bloqueio, e a política escala **um degrau sobre o turno anterior**: o teto
em bancada é baixo por construção. Isso não anula o efeito — um degrau a partir do acumulado 4 já
produz inclinação positiva — mas limita-lhe a magnitude, e é razão para esperar um efeito
modesto mesmo com a política a funcionar. A extensão torna o teste capaz de ver; não obriga a
haver o que ver.

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
