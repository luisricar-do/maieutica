# Bancada de avaliação da política de intervenção

Harness da avaliação descrita no Capítulo 4 da dissertação: executa o tutor sobre um banco de
itens de depuração, classifica cada turno com um **juiz automático** (LLM as a judge) e produz as
tabelas do Capítulo 5. Tudo por **chamadas HTTP** e o juiz é um modelo Gemini acionado por API.
Sem dependências novas: só a biblioteca padrão do Python 3.11.

As **três condições saem do mesmo serviço**, com o mesmo corpo de pedido e o mesmo registro por
turno — a comparação não pode ser confundida por diferença de infraestrutura:

| | O que é | Rota | Prefixos |
|---|---|---|---|
| **A** | o artefato: grafo roteador → analista → estrategista → comunicador | `POST /api/help` | todos |
| **B** | ablação da arquitetura: uma chamada, prompt socrático, sem grafo | `POST /api/help/single` (`promptVariant: "socratic"`) | só os de pressão |
| **C** | referência neutra: uma chamada, instrução de assistente genérico | `POST /api/help/single` (`promptVariant: "neutral"`) | todos |

O harness **não monta prompt nenhum**. Os dois prompts e o molde de contexto vivem no serviço,
congelados e com SHA-256 próprio; antes de cada corrida o `rodar` lê
`GET /api/help/single/prompts` e grava os três hashes no manifesto. Se um hash mudou desde a
corrida anterior, as duas corridas não são comparáveis — e o `congelar` recusa-se a fechar uma
execução cujo serviço já não é o que a gerou.

B corre só nos prefixos de pressão porque a ablação mede revelação sob pedido explícito.

As duas hipóteses que a bancada testa:

- **H1 — contingência.** A diretividade cresce com o acúmulo de estagnação e não cresce após
  progresso. Limiar descritivo fixado antes dos dados: taxa de contingência ≥ 0,70 em cada
  movimento — após bloqueio, **a partir do terceiro turno bloqueado** (ver abaixo).
- **H2 — robustez da não entrega.** Sob pedido explícito, o limite superior do IC de Wilson a 95%
  da taxa de revelação fica abaixo de 0,10.

## Fluxo

```
estados → validar → rodar → julgar → analisar → [exportar] → amostra-humana → kappa → congelar
```

| Comando | O que faz |
|---|---|
| `estados` | compila cada estado de código e roda os casos de teste **uma vez**, com o motor da IDE fora do navegador, e grava `errors`/`compilerErrorLines`/`casos_ok` no item |
| `validar` | verifica o banco: campos, movimentos anotados e, sobretudo, que nenhuma `fix_pattern` dispara num turno de referência |
| `prefixos` | mostra o que seria enviado (sem chamar nada); `--payload` imprime um corpo de `/api/help` |
| `rodar` | executa cada prefixo nas condições escolhidas, *n* vezes, em ordem aleatorizada, com reexecução em falha |
| `julgar` | classifica turnos gerados **e** turnos de referência com o juiz |
| `analisar` | H1, H2, calibração interna, descritivas, CSVs e tabelas `.tex` |
| `exportar` | emparelha cada turno gerado com as referências da posição, para as métricas de sobreposição rodarem no código do *benchmark* original |
| `amostra-humana` | planilha cega (sem condição, sem veredito do juiz) para os dois codificadores |
| `kappa` | κ humano×humano e consenso×juiz, mais precisão/cobertura do detector objetivo |
| `congelar` | manifesto de reprodutibilidade: commits, hashes de prompts, modelos observados |

## Preparação

```bash
# 1. serviço em modo de avaliação (RAG desligado, registro por turno ligado)
#    no local.settings.json:  "EVALUATION_MODE": "1", "INTERACTION_LOG_DIR": "<pasta>"
make start

# 2. modelo do juiz: pelo mesmo proxy e a mesma autenticação do tutor
python -m avaliacao juiz-modelos        # o que a chave do LiteLLM encaminha hoje
```

### Dois juízes, por custo

| | Modelo | Quando | Reportável |
|---|---|---|---|
| padrão | `gpt-4o` | desenvolver o harness, ensaiar o encanamento, conferir o banco | **não** |
| `--juiz-protocolo` | `gemini-3.1-pro-preview` | a corrida que vai para a tese | sim |

**O que o protocolo exige é a família do modelo, não o caminho até ele.** O juiz tem de ser de
família distinta da do tutor (`gpt-4o-mini`) — por isso o padrão barato, sendo OpenAI, serve só
para ensaio: `julgar` avisa e o manifesto grava `juiz_familia_distinta: false`, que o `resumo.md`
repete em negrito. `JUIZ_MODELO` e `--juiz-modelo` continuam sobrepondo-se aos dois.

Trocar de juiz **re-julga tudo**: um juízo do modelo A não conta como feito para o modelo B, para
não produzir uma amostra com dois juízes misturados. Os dois conjuntos convivem no mesmo
`juizos.jsonl`; `analisar` usa um só (o do manifesto, ou `--juiz-modelo`) e declara qual no
cabeçalho do resumo. O resumo de `julgar` traz o consumo em *tokens*, para dimensionar o custo da
corrida inteira a partir de um ensaio pequeno.

Dois transportes:

| `JUIZ_PROVEDOR` | Autenticação | Quando |
|---|---|---|
| `litellm` (padrão) | `LITELLM_API_KEY`, a mesma do tutor | o proxy encaminha o modelo do juiz |
| `gemini` | `GEMINI_API_KEY` (Google AI Studio) | o proxy não tem modelo Gemini na chave |

O modelo é *preview*: o identificador pode mudar ou sair do ar entre uma corrida e outra. O
manifesto grava a versão como a API a devolveu (`juiz_observado`), que é o que o congelamento
exige; se o identificador mudar no meio da coleta, isso é uma quebra de comparabilidade e tem de
ser declarada, não silenciada.

`julgar` confere o modelo contra `/v1/models` **antes** de começar e, se o proxy não o
encaminhar, para e lista o que está disponível. Se o modelo do juiz for da mesma família do
tutor, o comando não bloqueia mas imprime aviso, e o manifesto grava
`juiz_familia_distinta: false` — o resultado fica marcado como não reportável na origem.

Variáveis reconhecidas (o `local.settings.json` da raiz é lido como conveniência):
`AVALIACAO_API_BASE` (padrão `http://localhost:7071/api`), `LITELLM_BASE_URL`, `LITELLM_API_KEY`,
`LITELLM_MODEL`, `JUIZ_MODELO`, `JUIZ_PROVEDOR`, `GEMINI_API_KEY`, `AVALIACAO_PARALELISMO`,
`AVALIACAO_TIMEOUT`, `PORTUGOL_RUNNER`.

## Execução

```bash
python -m avaliacao estados                      # uma vez, depois de mexer no banco
python -m avaliacao validar
python -m avaliacao rodar --simular              # quantas chamadas isso dá
python -m avaliacao rodar --execucoes 3          # condições A, B e C
python -m avaliacao rodar --condicoes A,B --execucoes 3   # subconjunto, se quiser
python -m avaliacao julgar                       # ensaio barato (gpt-4o)
python -m avaliacao julgar --juiz-protocolo      # corrida reportável (gemini-3.1-pro-preview)
python -m avaliacao analisar
python -m avaliacao amostra-humana --tamanho 150
# … os dois codificadores preenchem codificador_1.csv e codificador_2.csv …
python -m avaliacao kappa
python -m avaliacao congelar
```

Toda etapa é **retomável**: o que já está registrado não é refeito, e um juízo que falhou é
reexecutado na passagem seguinte. Cada corrida vive em `execucoes/<id>/`:

```
execucoes/<id>/
  manifesto.json        commits, hashes de prompt, modelos observados, parâmetros
  turnos.jsonl          um registro por chamada (condição, execução, latência, resposta,
                        finish_reason, tokens, hashes do prompt e do molde em B e C)
  juizos.jsonl          um registro por turno julgado (gerado ou de referência)
  analise/              turnos_julgados.csv, h1_*.csv, h2_pedidos.csv, sensibilidade_*.csv,
                        descritivas_por_condicao.csv, resumo.md, tabelas/*.tex
  sobreposicao.jsonl    emparelhamento gerado × referências (só depois de `exportar`)
  validacao_humana/     planilhas dos codificadores, mapa cego, divergencias.csv, kappa.json
```

`h1_turnos.csv` é a entrada do modelo ordinal misto de H1 (statsmodels ou R), que fica fora deste
pacote justamente para mantê-lo sem dependências. O arquivo traz **todas** as condições, para as
descritivas; a coluna `entra_na_inferencia` marca as linhas da inferência, que corre **só sobre a
condição A** — B e C não têm política de contingência a testar.

### O limiar de 0,70 não é sobre a taxa agregada

A expectativa de 0,70 após bloqueio vale **a partir do terceiro turno bloqueado**: nos dois
primeiros a política prevê sustentar o nível, e uma taxa baixa ali é aderência ao escalonamento
retardado, não falha de contingência. Por isso `analisar` reporta três taxas — a agregada
(`apos_bloqueio`), a que decide o limiar (`apos_bloqueio_sustentado`) e a de progresso — e abre a
contingência por número de estagnações acumuladas em `h1_bloqueio_por_estagnacao.csv`.

### Efeito do pedido explícito, e sensibilidade

`analisar` reporta P(revelação | pedido) e P(revelação | outros) **e a diferença entre as duas**,
com intervalo de Newcombe a 95% — dois números soltos não dizem se o pedido explícito aumenta a
revelação. Conta também o roteamento dos turnos de A (`roteamento_A`): o roteador está fora do
escopo da avaliação, mas um prefixo classificado como fora de escopo recebe resposta fixa, e a
ocorrência tem de aparecer.

A sensibilidade sai aberta por `origem`, `prioridade` e `tipo_bug` em `sensibilidade_*.csv`, com
diretividade média, taxa de revelação com IC e fidelidade média. Os itens traduzidos não são os
originais: a leitura tem de poder separar as origens antes de generalizar.

### Métricas de sobreposição

BLEU-4, ROUGE-L e BERTScore são calculadas **com o código do *benchmark* original**, não aqui —
BERTScore exigiria um modelo neural, e a bancada é stdlib por desenho. `exportar` grava
`sobreposicao.jsonl` com um registro por turno gerado (`hipotese` mais `referencias`, o turno do
tutor humano da posição e as suas alternativas anotadas), pronto para esse código consumir. Só
prefixos de referência entram: os de pressão não têm turno humano correspondente.

### Amostra humana

A planilha cega leva turnos **gerados e de referência na mesma folha** — separá-los entregaria a
origem ao codificador. Por omissão, 180 gerados (os ~150 da tese mais ~30 para acomodar a
condição B) e 30 de referência; `--tamanho` e `--tamanho-referencia` ajustam. A origem de cada
linha fica só em `mapa_amostra.json`, que o codificador não vê.

### Truncamento

`rodar` conta, e `analisar` reporta por condição, a taxa de `finish_reason == "length"` — turnos
cortados no limite de tokens. O limite (300) é do comunicador, que em A só traduz um plano
interno; em B a mesma chamada tem de analisar, decidir e falar. Um turno cortado seria
classificado com diretividade errada e o viés cairia todo de um lado da comparação. Primeiro
medir: o limite não se mexe antes de haver número.

## Banco de itens

Um arquivo JSON por diálogo em `banco/`. Campos do formato de Al-Hossami (`problem`, `bug_code`,
`bug_desc`, `bug_fixes`, `unit_tests`, diálogo com alternativas) mais os que este trabalho
acrescenta:

| Campo | Papel |
|---|---|
| `tipo_bug` | `sintaxe`, `logica`, `limite`, `fluxo_dados`, `tipo`, `laco_infinito` |
| `estados_codigo` | um por estado do código no diálogo; `errors`/`compilerErrorLines`/`casos_ok` são preenchidos por `estados` |
| `estado_solucao` | estado terminal, com todas as correções aplicadas; não aparece no diálogo e é o único que pode não ser usado por um turno |
| `fix_patterns` | regex das correções aceitas → detector objetivo do nível 3 |
| `anchor_tokens` | linhas, variáveis e construtos do defeito → ancoragem |
| `dialogo[].movimento` | movimento anotado de cada turno do estudante (o de abertura é `NENHUM`) |
| `revisado_por` | segundo docente; `null` enquanto não revisado |

Os prefixos de pressão **não** estão no banco: são gerados por expansão, quatro por item (dois
após o primeiro turno do tutor, dois após o terceiro), com as cinco frases do apêndice sorteadas
sem reposição e semente fixa.

**Estado atual:** três itens, os cenários 1, 2 e 3 da dissertação, com diálogo de referência e
anotação de movimento redigidos pelo autor e ainda **sem revisão do segundo docente**. Faltam os
18 a 22 diálogos traduzidos do *benchmark* e os outros três cenários da dissertação para chegar
aos 24 a 28 itens previstos.

## Decisões do protocolo que o código implementa

- `hintLevel` fixo em 1 e `includeDocumentation` sempre `false`; nenhuma condição recebe `bug_desc`.
- Turnos anteriores do tutor no prefixo são os **de referência**, nunca os gerados.
- Nível 3 em código é decidido pelo detector objetivo; 0 a 2 e nível 3 em prosa, pelo juiz.
- O detector é relativo ao código vigente do prefixo: padrão de correção que o estudante já
  aplicou não conta como revelação (citar a linha corrente é ancoragem). `validar` rejeita,
  em sentido contrário, padrão que já case o **código inicial**.
- O juiz não recebe a condição de origem, roda a temperatura 0 e devolve uma justificativa de uma
  frase, usada para auditoria e não como métrica.
- O juiz também classifica os turnos de referência humanos: é daí que vêm o `d_{k-1}` da taxa de
  contingência em bancada e a calibração interna dos limiares.
- Manter o nível 2 após bloqueio conta como contingente, porque subir seria a revelação que H2
  proíbe.
- A escalada ao nível 2 é lida **sob estagnação persistente** (≥ 2 turnos bloqueados acumulados,
  porque a política sustenta o nível nos dois primeiros por projeto) e vem com a fração de
  trajetórias que **nunca** chegam ao nível 2 — descartá-las puxaria a mediana para baixo.
- κ ponderado usa a escala declarada da variável (diretividade 0–3, fidelidade 1–3), não a
  observada na subamostra. κ **indefinido** (uma só categoria) sai em `indefinidos` e não conta
  como validação: `kappa` devolve código 1.
- `validar` separa **problemas** (invalidam o banco) de **avisos** (o revisor tem de ver): o
  principal é a anotação de movimento discordar da regra objetiva dos estados. Com edição de
  código é a regra objetiva que a medida usa; sem edição decide o texto e o aviso é só uma
  confirmação. Deixar de estourar o tempo conta como progresso objetivo (itens `laco_infinito`).
- Prefixos de pressão: dois por âncora ("cedo" após o 1.º turno do tutor, "tarde" após o 3.º).
  Quando o diálogo é curto demais para as duas âncoras serem posições distintas, o item rende só
  os dois de "cedo" — melhor menos pressão do que um contraste de posição inexistente.
- Em H2 a unidade é o pedido, com decisão majoritária entre as execuções do prefixo.
- Falha técnica é reexecutada duas vezes e, persistindo, marcada e excluída do denominador.

## Ressalvas

- O juiz é **Gemini** por desenho — família distinta da do tutor, contra a auto-preferência. O
  transporte (proxy LiteLLM ou API da Google) é indiferente ao protocolo; a família não. O padrão
  `gpt-4o` existe por custo e ensaia o encanamento e nada mais: o aviso, o manifesto e o
  `resumo.md` registram que aquilo não é resultado.
- Nenhum número da análise automática é resultado antes da validação humana (κ ≥ 0,60).
- Os prefixos de pressão são artificiais por construção; a pressão real vem do uso em sala.
