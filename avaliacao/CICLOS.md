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
(`ESTAGNACAO` ou `REGRESSAO`) **sem edição de código**, e um `PROGRESSO` final — e sete turnos de
tutor de referência, um entre cada par. O turno de cortesia depois do defeito corrigido é cortado,
como o protocolo já manda cortar na tradução: viraria prefixo-ouro sem defeito a depurar. Rende
sete prefixos ouro, **seis deles com acumulado 1 a 6**, mais os quatro de pressão que a expansão
gera. O molde é `banco/tese_06_contagem.json`, e `banco/tese_07_soma_multiplos.json` é o primeiro
na profundidade nova.

O número sai da simulação (`analise_tese/poder_h1.R`), não de conveniência. Com 20 itens o
erro-padrão do efeito do acúmulo cai de 0,617 para 0,216: 79% de poder para um efeito de 0,6, e
detectável a 80% qualquer efeito a partir de 0,60. Com 10 itens seriam 51%; com 35, 92%.

A profundidade não se troca por quantidade. Vinte itens de profundidade 4 dão erro-padrão 0,364,
**pior** que dez de profundidade 6 (0,304), apesar de mais prefixos: o que conta é a dispersão do
acumulado entre prefixos, e `Var(1..4) = 1,25` contra `Var(1..6) = 2,92`.

Os itens novos correm em todas as condições, como os 25 existentes, para o banco continuar
uniforme e alimentar também as descritivas e a ablação. A corrida somativa passa de 1 860 para
cerca de 3 540 chamadas.

### Extensão concluída

Os vinte itens estão no banco, `tese_07` a `tese_26`, e o banco rende **167 prefixos
bloqueados** — o ponto de desenho exato que a simulação dimensionou para erro-padrão 0,216 e
79% de poder. A cobertura na faixa em que a política escala passou de 7 para 67 prefixos, e de
3 para 23 itens em 45.

As classes de defeito distribuem-se por `fluxo_dados` (8), `logica` (8), `limite` (3) e
`laco_infinito` (1). Todos os estados foram executados no motor headless: o estado com defeito
passa entre 0 e 2 dos 3 casos e o corrigido passa os 3, e onde o defeituoso passa algum é sempre
o caso degenerado ou aquele que o defeito não afeta.

Dois itens planeados caíram na verificação, e valem como registro do que o motor decide e a
intuição não. Um item de `tipo` por divisão inteira não existe: neste Portugol
`inteiro / inteiro` para destino `real` dá divisão real, e a truncagem só vem do destino
`inteiro`, que é o defeito que `tese_01_media` já tem. E um item de índice deslocado também não:
ler posição não inicializada do vetor aborta o programa em silêncio, com `executed` verdadeiro e
saída vazia, de modo que o estudante não veria número errado, veria nada.

Um terceiro caiu por análise errada minha, apanhada pela execução: numa contagem com sentinela,
ler antes de contar e contar antes de ler dão o mesmo total, porque o incremento conta o valor
anterior, que a condição já validou. Não havia defeito nenhum a depurar, e o item foi
substituído por dois laços `enquanto` que partilham a variável de controle sem a reiniciar.

### O que a extensão não resolve

Três coisas ficam declaradas antes, para não serem lidas depois como justificação.

Os 20 itens são todos `origem: tese`, redigidos pelo autor — que é também quem anota o movimento
e quem codifica a amostra humana, porque o estudo tem um só codificador e nenhum revisor externo
do banco, por desenho declarado na metodologia. A extensão concentra ainda mais o instrumento na
mesma mão: os itens construídos passam de 6 em 25 para 26 em 45, e com eles a fatia dos prefixos
bloqueados que existe porque o autor decidiu que existiria. É o custo de tornar o teste capaz, e
tem de aparecer nas limitações junto com o que já lá está sobre codificador único.

A sensibilidade por origem, que já está no plano analítico, é o único controlo disponível contra
isso, e deixa de ser decorativa: se H1 se sustentar nos itens `tese` e não nos traduzidos, a
leitura honesta é que o efeito vive no corpus construído, não que H1 se sustenta. No ciclo 1 o
coeficiente do acúmulo já diverge por origem — −0,975 em `tese` contra +0,579 em `al_hossami_v2`
—, portanto a divergência é esperada e a checagem é obrigatória.

Um agravante a registar: os turnos de tutor de referência dos itens novos são 160, e são o padrão
humano contra o qual o artefato é medido, a âncora a partir da qual ele escala em bancada e a
fonte do `d_{k-1}` da taxa de contingência. Se fossem gerados por modelo de linguagem, a bancada
deixaria de comparar o artefato com tutoria humana e passaria a comparar dois modelos. São
escritos pelo autor, como os 25 itens existentes, e `notas_traducao` de cada item novo registra a
procedência.

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

## Segunda correção, antes de o ciclo 2 existir

Escrito em 2026-09-15, com o ensaio feito e a corrida somativa por disparar. Vale a mesma regra
do topo deste documento: o que aqui está é anterior à corrida, e por isso conta.

### O nó de classificação do movimento

O artefato ganha um nó no grafo, entre o analista e o estrategista (`agents/classifier.py`). Ele
substitui **um** degrau da classificação do movimento — o do texto — por um estimador com modelo
de linguagem. A precedência da dissertação não muda: pedido explícito primeiro, regra do
compilador depois, texto por último; e o estimador cai de volta na regra determinística sempre
que não devolve rótulo.

A razão é de construto, não de desempenho. A regra textual lê "hipótese ou observação nova" como
progresso, e a dissertação chama **regressão** à hipótese incorreta afirmada. Decidir se a
hipótese está errada é julgar conteúdo contra o código, e nenhum padrão textual o faz — o próprio
docstring de `agents/movement.py` já o declarava fora de alcance. O nó vem depois do analista
porque é o diagnóstico que diz qual é o defeito, e sem isso não se julga se o estudante aponta
para ele.

Cada turno é estimado **só com o que existia até ele**: o rótulo do turno 2 não pode depender do
que o estudante disse no turno 5, sob pena de o contador deixar de ser o que a política teria
consumido naquele momento. O acumulador continua aritmético — soma em bloqueio, zera em
progresso. Estima-se o rótulo, não o acumulado.

O que **não** muda: o limiar de escalonamento continua em 4, o juiz continua
`gemini-3.1-pro-preview`, o critério de sustentação de H1 fica como está, e o pedido explícito —
condição de H2 — continua determinístico, fora do alcance do modelo. `rodar --simular` continua a
dizer 3 420: o nó é chamada interna do grafo, não requisição da bancada.

Cada turno passa a registar também o que a regra determinística teria dito
(`tutorMeta.movementBaseline`, `stagnationStreakBaseline`) e a origem do rótulo consumido
(`movementSource`). A comparação entre a regex e o estimador sai da própria corrida, sem a
repetir.

### A concordância medida antes de gastar a corrida

`scripts/concordancia_movimento.py` mede o contador derivado pelo artefato contra a
`estagnacao_acumulada` anotada no banco, nos 480 prefixos, sem juiz. Com o analista a correr de
verdade, e com o limiar da política a separar as faixas:

| | 0 | 1–3 | ≥ 4 | exata | por faixa |
|---|---:|---:|---:|---|---|
| banco (regressor de H1) | 253 | 160 | 67 | — | — |
| artefato: regra | 347 | 131 | 2 | 276/480 (57,5%) | 292/480 (61%) |
| artefato: regra + nó | 273 | 187 | 20 | 292/480 (60,8%) | 334/480 (70%) |

O nó melhora, e não resolve: 20 prefixos na faixa de escalonamento contra os 67 do banco. O
diagnóstico de porquê é a segunda coisa que este registo tem de fixar.

O estimador **não é perfeitamente reprodutível** entre corridas, mesmo com temperatura 0. No
ensaio de dois itens, `tese_07::k7` saiu com acumulado 1 onde a medição offline do mesmo prefixo
tinha dado 6 — um rótulo de meio do diálogo mudou e zerou o contador. Fica declarado antes: o
regressor derivado pelo artefato passa a ter variância de corrida que a regra determinística não
tinha, e a apuração tem de a reportar, não de a esconder. As três execuções de cada prefixo dão
como a medir.

### O banco está anotado sob duas regras incompatíveis

Cruzando, para cada turno de estudante do banco, o movimento anotado com o facto de ter havido
ou não edição de código:

| | PROGRESSO | ESTAGNACAO | REGRESSAO |
|---|---:|---:|---:|
| **25 itens do ciclo 1** — sem edição | 78 | 26 | 10 |
| **25 itens do ciclo 1** — com edição | 10 | 9 | 2 |
| **20 itens novos** — sem edição | **0** | 100 | 20 |
| **20 itens novos** — com edição | 20 | 0 | 0 |

A separação é total. Nos 25 itens do ciclo 1 o movimento é julgado pelo **conteúdo da fala**: 78
de 114 turnos sem edição são progresso. Nos 20 itens novos é julgado pelo **estado do código**:
nenhum dos 120 turnos sem edição é progresso, e os 20 progressos coincidem exactamente com a
única correção de código de cada item. Não é diferença de comportamento do estudante entre os
dois conjuntos; é diferença de regra de anotação.

A consequência aritmética é direta: nos itens novos, a `estagnacao_acumulada` anotada **iguala o
índice do turno do estudante em 140 dos 160 turnos**, e as 20 exceções são o turno final de cada
item, o da correção. Por outras palavras, nesses itens o regressor de H1 é a contagem de turnos
com outro nome — que é a variável do defeito do ciclo 1, agora do lado da medida em vez do lado
da política.

É também de onde vem o salto de cobertura de 7 para 67 prefixos na faixa de escalonamento, que a
seção "Extensão concluída" credita à extensão: 60 dos 67 vêm dos itens novos, e vêm da regra de
anotação, não de diálogos mais difíceis. Um diálogo de sete turnos sem edição produz
mecanicamente o acumulado 1, 2, 3, 4, 5, 6.

E explica por que nenhum classificador de conteúdo — regex ou modelo — reproduz essa faixa: o
rótulo que ele teria de acertar não depende do conteúdo. Nos três itens em que o nó acerta os
prefixos todos (`tese_07`, `tese_08`, `tese_23`), acerta porque ali as falas são, de facto,
hipóteses erradas e bloqueio do princípio ao fim; nos outros dezassete, o estudante descreve o
defeito correctamente a pedido do tutor e o banco chama-lhe estagnação.

### Decisão: opção 1, e o que ela custou

Reanotados os 20 itens novos pela regra de conteúdo do ciclo 1, extraída dos próprios 25 itens
antigos e não inventada agora. **98 dos 100 turnos mudaram** — 93 `ESTAGNACAO`→`PROGRESSO` e 5
`ESTAGNACAO`→`REGRESSAO`; dois ficaram. A tabela turno a turno, com a justificação de cada rótulo
que não virou progresso e das duas chamadas discutíveis, está em `avaliacao/REANOTACAO_CICLO2.md`
e é reproduzível por `scripts/reanotar_movimento.py`. `referencia_autoria` continua
`autor_com_assistencia`.

O efeito sobre o instrumento:

| | prefixos bloqueados | faixa ≥ 4 | itens que atingem ≥ 4 |
|---|---:|---:|---:|
| antes da extensão (25 itens) | 47 | 7 | 3 |
| com a extensão, anotação anterior | 167 | 67 | 23 |
| com a extensão, reanotada (45 itens) | **74** | **7** | **3** |

A faixa de escalonamento volta a **exactamente** os 7 prefixos e os 3 itens que a seção
"Extensão concluída" regista como o ponto de partida — o que é a verificação de que a
reanotação aterra mesmo no construto do ciclo 1, e não num terceiro. A estagnação acumulada
máxima em qualquer item novo passa a ser **2**: nenhum deles chega ao limiar.

Dito sem rodeios: sob a regra de conteúdo, **os 20 itens não contêm bloqueio sustentado**. O
estudante responde correctamente a quase todas as perguntas socráticas; o que cada item tem é
uma hipótese errada, no sexto turno, e mais nada. Eles acrescentam 27 prefixos bloqueados, todos
com acumulado 1 ou 2 — engrossam a base da distribuição e não tocam no limiar.

O dimensionamento que a extensão justificava — erro-padrão 0,216 e 79% de poder — **fica sem
efeito**, porque foi calculado sobre os 167 prefixos bloqueados e 67 na faixa. O que existe agora
é 74 e 7. Refazer o cálculo de poder sobre estes números é passo obrigatório antes de a corrida
valer como somativa.

### O nó de classificação não se justifica, e fica desligado

Repetida a medição contra o banco reanotado, o estimador deixa de ganhar:

| | 0 | 1–3 | ≥ 4 | exacta |
|---|---:|---:|---:|---|
| banco (regressor de H1) | 384 | 89 | 7 | — |
| artefato: regra | 347 | 131 | 2 | **321/480 (66,9%)** |
| artefato: regra + nó | 271 | 190 | 19 | 302/480 (62,9%) |

A vantagem que o nó tinha era contra a anotação pelo estado do código; contra o conteúdo ele
perde na concordância exacta, empata por faixa (328 contra 326) e escala a mais. Nos **7**
prefixos que o regressor põe na faixa, os dois classificadores escalam nos **mesmos 2**; o nó
acrescenta 17 escalonamentos onde o regressor diz que não devia haver nenhum.

Por isso o nó passa a depender de `CLASSIFICADOR_DE_MOVIMENTO`, com padrão `regra`: o artefato
que vai à corrida é o pré-registado. `modelo` liga o nó, e é assim que a corrida A/A se faz sem
tocar em código. O módulo, os testes e `scripts/concordancia_movimento.py` ficam no repositório —
a comparação é resultado do capítulo, não código morto.

### O poder, que é o número que decide o resto

Populações reconciliadas primeiro, porque se divergissem divergiria tudo: os **74** prefixos
bloqueados e os **96** com acumulado ≥ 1 correm sobre os mesmos 480. Os 74 são "o último turno foi
bloqueio"; os 96 são "o contador estava positivo". A diferença são exactamente 22 prefixos de
pressão cuja última fala é `PEDIDO_EXPLICITO`, que transporta o contador sem o alterar — esses são
população de H2. Os 74 são todos ouro, e são o que `poder_h1.R` consome como `obs`. Sem divergência.

`analise_tese/poder_h1_corpus.R` corre a mesma maquinaria de `poder_h1.R` — mesmos limiares e
mesmas componentes de variância do ajuste do ciclo 1 — sobre os bloqueados do banco reanotado.

| | prefixos bloqueados | itens | Var(acumulado) | EP simulado | poder (β = 0,6) |
|---|---:|---:|---:|---:|---:|
| ciclo 1 (25 itens) | 47 | 20 | 2,152 | 0,565 | 0,17 |
| banco reanotado (45 itens) | 74 | 40 | 1,573 | ~0,57 | 0,18 |

**A extensão não comprou precisão nenhuma.** O n sobe 57% e a Var(acumulado) desce 27%, e os dois
cancelam-se quase exactamente — os 27 prefixos que os itens novos acrescentam entram todos em 1 ou
2, onde a contribuição para a variância do regressor é a menor que há.

#### Um aviso sobre todos os números de poder deste documento

O EP simulado tem **DP de 0,223 entre réplicas**. Com as R = 40 réplicas que `poder_h1.R` usa, a
média carrega erro de Monte Carlo de **±0,035**, isto é, um intervalo típico de [0,495; 0,634] para
a mesma quantidade. O **0,617** que a seção "O que o ciclo 1 tinha como detectar" regista e o 0,562
que esta corrida produziu são **a mesma quantidade com sementes diferentes**; a estimativa estável,
com 220 réplicas, é **0,565 ± 0,015**. O mesmo ruído está no **0,216 e nos 79%** que dimensionaram a
extensão, e vê-se a olho na varredura: a célula de 15 itens a profundidade 6 saiu com EP 0,471,
entre 0,285 aos 10 e 0,217 aos 20 — fora de ordem, por ruído. Qualquer número de poder que vá ao
capítulo precisa de R ≥ 200.

#### Quantos itens com bloqueio sustentado seriam precisos para 80%

| profundidade do item novo | itens necessários | observação |
|---|---|---|
| 6 (acumulado chega a 6) | **~21** | confirmado por duas sementes independentes na célula de 20 |
| 4 (acumulado chega a 4) | **não chega** | 40 itens dão poder 0,61; 80% fica fora de alcance prático |

### A rota do corpus não é viável, e é isso que fecha a questão

Cruzando a exigência com a taxa base de bloqueio sustentado no banco que existe:

| origem | itens | chegam a ≥ 4 | chegam a ≥ 6 |
|---|---:|---:|---:|
| `al_hossami_v2` (derivados de diálogos reais) | 19 | 2 | **1** |
| `tese` (escritos pelo autor) | 26 | 1 | **0** |

O banco inteiro tem **um** item de profundidade 6, e é `0_0_fibonacci_t3` — derivado de dados reais,
não escrito. Ter 80% de poder por via de corpus exigiria escrever **~21 itens tão bloqueados quanto
o item mais bloqueado dos 45**, com taxa base autoral de 0 em 26. A tentativa deliberada de 20 itens
de bloqueio produziu 0. Não é uma rota cara: é uma rota que não existe.

### O achado metodológico — e é contribuição, não limpeza

Para um prefixo chegar a ≥ 4 é preciso um estudante que, ao longo de quatro turnos seguidos, **não
edita código e não avança conceptualmente**. Foram escritos 20 itens com a intenção explícita de
conter isso e saíram 20 itens sem nenhum. Não foi desleixo: ao escrever um estudante a conversar com
um tutor socrático, o que sai naturalmente é um estudante que responde bem às perguntas. **"Não
edita" e "está encravado" são coisas diferentes, e a escrita de diálogo colapsa-as** — foi por isso
que a anotação dos 20 itens derivou para o estado do código sem que ninguém o decidisse.

Daí três consequências que o capítulo deve reportar:

1. Bloqueio sustentado sob a regra de conteúdo é **raro** (3 em 45 itens a ≥ 4; 1 em 45 a ≥ 6) e
   **difícil de construir autenticamente**. Isso justifica retroactivamente por que o construto
   precisa da regra objectiva: é ela que faz o trabalho pesado onde o bloqueio ocorre sozinho.
2. Onde o bloqueio ocorre sozinho é **em sala**, com estudantes a sério — e o pré-registo já o
   declara: *"Em sala a regra objetiva (casos de teste + compilação) prevalece quando há edição; o
   juiz decide só o texto."*
3. Se houver segunda tentativa de corpus, ela tem de correr o portão **item a item, à medida que se
   escreve** — `scripts/bloqueio_sustentado.py`, que dá o perfil de acumulado de um item e diz se
   passa. Item que não mostra bloqueio sustentado não conta. Esse ciclo fechado é o que distingue a
   tentativa 2 da tentativa 1, e da primeira vez a ferramenta não existia.

### O defeito do classificador: dois portões, um critério, dois resultados negativos

O critério foi declarado antes das duas medições, em `scripts/concordancia_movimento.py` e
reafirmado em `scripts/gate_ancora.py`: uma alteração ao classificador entra **se a concordância
exacta e a concordância por faixa melhorarem, sem escalar a mais**. Duas candidatas foram medidas
contra ele, e as duas reprovaram.

| candidata | exacta | por faixa | escala ≥ 4 (dentro / fora dos 7) | veredito |
|---|---|---|---|---|
| regra actual (referência) | 321/480 (66,9%) | 328/480 (68,3%) | 2 (2 / 0) | — |
| **+ nó de classificação** (modelo) | 302/480 (62,9%) | 326/480 (67,9%) | 19 (2 / **17**) | reprova |
| **+ correcção da âncora** (número ancora a partir de 2 dígitos) | 306/480 (63,8%) | 319/480 (66,5%) | 4 (**4** / 0) | reprova |

A correcção da âncora — estender aos números a regra que `_ancorado_no_codigo` já aplica aos
identificadores, onde token de menos de três caracteres não discrimina — merece a nota que o seu
veredito esconde: **duplica o escalonamento correcto, de 2 para 4 dos 7, sem um único falso**. Perde
mesmo assim, porque dos 34 prefixos que mexe, 2 aproximam-se do banco e 17 afastam-se. Fica como
registo em `scripts/gate_ancora.py`, sem chave de configuração: uma chave por candidata reprovada é
superfície a manter para nada.

### Onde vive a discordância, degrau a degrau

`_classify_by_text` é uma escada de sete degraus. Para cada turno que o texto decide, qual disparou
e se acertou (`scripts/onde_discorda.py`):

| degrau | n | acerta | % | IC 95% (Wilson) | principal discordância |
|---|---:|---:|---:|---|---|
| `stall` | 26 | 19 | 73,1% | [53,9; 86,3] | PROGRESSO→ESTAGNACAO 7 |
| `repeticao` | 1 | 0 | — | — | PROGRESSO→ESTAGNACAO 1 |
| `curto` | 1 | 0 | — | — | PROGRESSO→ESTAGNACAO 1 |
| `hipotese` | 79 | 48 | 60,8% | [49,7; 70,8] | **REGRESSAO→PROGRESSO 26**, ESTAGNACAO→PROGRESSO 5 |
| `ancora` | 70 | 59 | 84,3% | [74,0; 91,0] | REGRESSAO→PROGRESSO 6, ESTAGNACAO→PROGRESSO 5 |
| `fora_do_foco` | 74 | 8 | 10,8% | [5,6; 19,9] | **PROGRESSO→ESTAGNACAO 63** |
| **total** | **251** | **134** | **53,4%** | [47,2; 59,5] | |

`repeticao` e `curto` vão como contagem: com n = 1 uma percentagem não diz nada.

**Correcção do n, que também corrige o que esta seção dizia antes.** A unidade é o par
**(item, turno)**, não o prefixo. Os prefixos do mesmo item partilham turnos — o turno 0 aparece em
todos os prefixos do item —, portanto contar por prefixo multiplica cada turno pelo número de
prefixos que o contêm, e enviesa para os turnos iniciais. A contagem por prefixo dava ~4× este n. A
versão anterior desta seção reportava "42 prefixos ouro em que o banco diz bloqueio e o artefato diz
`PROGRESSO`", com as causas repartidas em 31/6/5: esse número tinha o mesmo defeito **e** contava só
uma das direcções do erro. A tabela acima substitui-o.

O que ela mostra e a contagem por prefixo escondia: o maior bolo de erro não é o falso progresso, é
o **falso bloqueio** — `fora_do_foco` chama estagnação a 63 de 74 turnos que o banco anota
`PROGRESSO`. A âncora, que foi a candidata atacada, é o **melhor** degrau da escada (84,3%).

### O tecto, e por que nenhuma correcção parcial serve

Substituindo o veredito de um degrau pelo do banco (oráculo), até onde sobe a concordância do
acumulado:

| oráculo em | 0 | 1–3 | ≥ 4 | exacta | por faixa |
|---|---:|---:|---:|---|---|
| banco | 384 | 89 | 7 | — | — |
| nenhum (regra actual) | 347 | 131 | 2 | 321/480 (66,9%) | 328/480 (68,3%) |
| só `ancora` | 330 | 144 | 6 | 335/480 (69,8%) | 345/480 (71,9%) |
| só `hipotese` | 308 | 161 | 11 | 346/480 (72,1%) | 367/480 (76,5%) |
| `hipotese` + `ancora` | 291 | 169 | **20** | 364/480 (75,8%) | 386/480 (80,4%) |
| todos (limite superior) | 383 | 90 | **7** | 479/480 (99,8%) | 479/480 (99,8%) |

A leitura estrutural está na última coluna contra a penúltima linha. **Os erros da escada
cancelam-se.** `fora_do_foco` estagna a mais (63 falsos bloqueios) e `hipotese` progride a mais (26
regressões lidas como progresso); o saldo é o 2 da faixa que a regra actual produz. Corrigir só os
dois degraus que se sabe corrigir leva a faixa a **20** — passa dos 7 do banco e escala a mais, que
é exactamente o que reprovou o nó. Só com o oráculo em **todos** os degraus se aterra nos 7, e aí a
concordância é 99,8%.

Ou seja: não há correcção parcial segura da regra textual. O que faltaria é um classificador de
texto quase perfeito, e "quase perfeito" aqui significa julgar se a hipótese afirmada está certa —
que é precisamente o que o nó tentou e fez pior. As duas reprovações e o tecto dizem a mesma coisa
por três vias.

### A régua, declarada

Tudo acima é medido contra a **anotação de movimento do banco**, que é o regressor de H1 e que foi
reanotada neste mesmo ciclo pela regra de conteúdo (`avaliacao/REANOTACAO_CICLO2.md`). Não é
verdade externa: é a régua do estudo, escolhida e documentada, e qualquer leitura destes números
herda as escolhas dessa reanotação — incluindo as duas chamadas que lá ficam marcadas como
discutíveis.

A favor: isto mede o **classificador sobre o corpus**, não a corrida. Não depende de `cap5`, não
muda quando ela correr, e por isso escreve-se agora, antes, como tudo o resto neste ciclo.

### O que fica em aberto, e o que deixou de estar

**Deixou de estar em aberto a rota do corpus.** A medição acima fecha-a: ~21 itens de profundidade
6 contra uma taxa base autoral de 0 em 26. Não é decisão, é impossibilidade prática.

**Deixou de estar em aberto esperar para correr.** A única razão real para adiar `cap5` era não
correr duas vezes caso viessem itens novos. Não vêm. E a corrida não produz só o coeficiente do
escalonamento: produz **H2 com 180 prefixos de pressão** — quase o dobro do ciclo 1, onde o
intervalo falhou os 5% por 0,004 —, a **metade do progresso de H1**, que a reanotação deixou
fortíssima (384 prefixos em acumulado 0), as descritivas, a ablação, e sobretudo a
**amostra humana**, que é o caminho crítico de três semanas e cuja recodificação diferida só é
elegível a partir de 2026-10-03.

**Fica em aberto a metade do escalonamento de H1**, e ela depende da sala, que está declarada,
submetida e bloqueada pelo parecer do CEP (`Tese/docs/todo-defesa.md`, `Tese/plataforma_brasil/`).
O desenho já prevê a divisão — o plano do Capítulo 5 diz "H1 em bancada **e em sala**":

- **Sala acontece** → a bancada não precisa de item nenhum. Reporta-se a metade do progresso e a
  sustentação em 1–3 (89 prefixos), e a metade do escalonamento vai para a sala, onde o bloqueio
  sustentado ocorre sozinho e a regra objectiva já é a declarada no pré-registo.
- **Sala não acontece** → declara-se a metade do escalonamento **não testável em bancada**, com a
  taxa base medida acima como justificação. Fabricar itens até a faixa encher não é opção.

Nota sobre o limiar descritivo: a contingência declarada no pré-registo lê-se "a partir do 3.º
turno bloqueado", e há **10** prefixos com acumulado ≥ 3 — três a mais do que os 7 do limiar da
política, e a mesma ordem de grandeza.

## Retomar daqui

Escrito em 2026-09-15, com a extensão do banco concluída e o ciclo 2 por correr.

### O que já está feito

O artefato consome a estagnação acumulada (`agents/movement.py`, `agents/strategist.py`), a IDE
envia o estado de código por turno do estudante, o banco tem 45 itens e **74** prefixos
bloqueados (eram 167 antes da reanotação da seção anterior), e os scripts de apuração aceitam a execução por `AVALIACAO_EXECUCAO`, com `cap4` como padrão.

### O que falta configurar

Só uma coisa: **`INTERACTION_LOG_DIR` não está no `local.settings.json`**. `EVALUATION_MODE`,
`LITELLM_BASE_URL` e `LITELLM_API_KEY` já estão. O juiz sai pelo LiteLLM com a mesma
autenticação do tutor, portanto não é preciso `GEMINI_API_KEY`.

### A sequência

```bash
make start                                     # serviço em modo de avaliação

# ensaio do encanamento, barato, antes de gastar a corrida inteira
python -m avaliacao rodar --execucao ensaio-ciclo2 \
    --itens tese_07_soma_multiplos,tese_08_troca_valores --execucoes 1
python -m avaliacao julgar --execucao ensaio-ciclo2      # juiz barato, NÃO reportável

# a corrida que vai para o capítulo
python -m avaliacao rodar --simular --condicoes A,B,C --execucoes 3   # confere: 3 420
python -m avaliacao rodar --execucao cap5 --condicoes A,B,C --execucoes 3
python -m avaliacao julgar --execucao cap5 --juiz-protocolo           # gemini-3.1-pro-preview
python -m avaliacao analisar --execucao cap5
python -m avaliacao amostra-humana --execucao cap5

# ... codificação cega; TRÊS SEMANAS; recodificação do terço ...
python -m avaliacao kappa --execucao cap5

AVALIACAO_EXECUCAO=cap5 .venv/bin/python -m analise_tese.apurar_h1_h2
AVALIACAO_EXECUCAO=cap5 .venv/bin/python -m analise_tese.preparar_h1_modelo
Rscript analise_tese/h1_ordinal.R
```

### Números de controlo

Se algum destes não bater, parar e perceber porquê antes de seguir: **3 420** chamadas de
geração, **3 720** vereditos do juiz, **480** prefixos (300 ouro + 180 pressão), **74** prefixos
bloqueados — eram 167 antes da reanotação da seção anterior, e o número que conta é este.
A amostra humana continua em 210 turnos — é absoluta e não acompanha o corpus, logo a
codificação não fica maior do que foi no ciclo 1.

### O caminho crítico é a codificação, não a corrida

`rodar` e `julgar` são horas de relógio. A partir da `amostra-humana` são no mínimo três semanas
até existir κ, porque a recodificação do terço só vale diferida. Marcar a data da primeira rodada
é o que determina tudo o que vem depois.

### O que não se mexe

Os compromissos das seções acima valem como estão: o resultado do ciclo 2 vai para o capítulo
seja qual for, o critério de sustentação de H1 não muda, o limiar de escalonamento do artefato
não muda, e o juiz continua a ser `gemini-3.1-pro-preview` — trocá-lo quebraria a comparação
entre os dois ciclos.

### Dois pontos em aberto

Os vinte itens novos estão com `referencia_autoria: autor_com_assistencia`. Reescritos os turnos
de tutor na voz do autor, o campo passa a `autor` e o item volta à calibração humana dos
limiares. Enquanto estiver como está, `apurar_h1_h2` exclui esses turnos dessa calibração e
reporta quantos excluiu.

E H2 ganha poder sem ter sido planeado: os prefixos de pressão passam de 100 para 180, portanto o
n da hipótese quase dobra. No ciclo 1 o intervalo foi [0,002; 0,054] e falhou os 5% por 0,004.
