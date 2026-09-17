# Portugol Tutor API

**Repositório:** [github.com/luisricar-do/maieutica](https://github.com/luisricar-do/maieutica)

Backend **multiagente (MAS)** com **tutor socrático** para integração com um fork do **Portugol Webstudio** (portugol.dev), desenvolvido como artefato de dissertação de Mestrado em Informática na Educação (UNIFEI).

O serviço expõe uma **Azure Function** em Python que orquestra dois agentes via **LangGraph**:

1. **Agente Analista** — recebe código Portugol e mensagens de erro do compilador e produz um **diagnóstico estruturado** (JSON).
2. **Agente Tutor Socrático (ADA)** — recebe o diagnóstico e o histórico da conversa e devolve **apenas orientação por perguntas**, sem entregar a solução pronta.

## Arquitetura (visão geral)

```
┌─────────────────────┐     POST /api/help      ┌──────────────────────┐
│  Portugol Webstudio │ ───────────────────────► │   Azure Function     │
│  (frontend / IDE)   │ ◄─────────────────────── │   (function_app.py)  │
└─────────────────────┘     JSON (CORS no host) └──────────┬───────────┘
                                                             │
                                                             ▼
                                                  ┌──────────────────────┐
                                                  │      LangGraph       │
                                                  │   analyst → tutor    │
                                                  └──────────┬───────────┘
                                                             │
                        ┌────────────────────────────────────┴────────────────────────┐
                        ▼                                                         ▼
               ┌─────────────────┐                                       ┌─────────────────┐
               │ Agente Analista │                                       │  Tutor (ADA)   │
               │ (via proxy      │                                       │ (via proxy      │
               │  OpenAI /v1)    │                                       │  OpenAI /v1)    │
               └────────┬────────┘                                       └────────┬────────┘
                        │                                                         │
                        └────────────────────────┬────────────────────────────────┘
                                                 ▼
                                    ┌────────────────────────┐
                                    │  LiteLLM (ou proxy     │
                                    │  OpenAI-compatível)    │
                                    └────────────────────────┘
```

## Stack

| Componente        | Tecnologia                          |
|-------------------|-------------------------------------|
| Runtime           | Python 3.11                         |
| Serverless        | Azure Functions v2 (modelo por decoradores) |
| Orquestração      | LangGraph                           |
| LLM               | Modelo configurado no [LiteLLM](https://docs.litellm.ai/) (ou proxy compatível) via `langchain-openai` + `LITELLM_BASE_URL` |
| Dependências (dev)| Poetry, Ruff, pytest, pytest-asyncio, Makefile (`make test` / `make start`) |

## Estrutura de pastas

A API Python vive na **raiz deste repositório** (`maieutica/`):

```
maieutica/   (raiz — também o nome do pacote Poetry: portugol-tutor-api)
├── agents/
│   ├── __init__.py
│   ├── analyst.py      # Diagnóstico estruturado (JSON)
│   ├── tutor.py        # Tutor socrático ADA
│   ├── llm.py          # Cliente OpenAI-compatível (LiteLLM / proxy)
│   └── graph.py        # Grafo LangGraph (analyst → tutor)
├── services/
│   ├── __init__.py
│   ├── tutor_help.py         # Caso de uso: /api/help (validação + grafo)
│   ├── tutor_help_stream.py  # SSE: /api/help/stream (diagnóstico + tokens)
│   ├── telemetry.py          # Caso de uso: /api/telemetry (validação + NDJSON)
│   ├── telemetry_store.py    # Persistência dos lotes no Azure Blob Storage
│   └── ping.py               # Health: resposta JSON para /api/ping
├── tests/
│   ├── test_analyst.py
│   ├── test_tutor.py
│   ├── test_graph.py
│   ├── test_help_service.py
│   ├── test_help_stream.py
│   ├── test_ping.py
│   ├── test_llm.py
│   ├── test_telemetry.py
│   ├── test_telemetry_store.py
│   └── conftest.py
├── scripts/
│   └── fetch_telemetry.py   # Baixa e consolida a telemetria (NDJSON + CSV)
├── function_app.py     # HTTP: /api/ping, /api/help, /api/help/stream, /api/telemetry
├── Makefile            # atalhos: make test / make dev / make start / make watch
├── pyproject.toml      # Fonte da verdade (Poetry)
├── requirements.txt    # Export para deploy na Azure
├── host.json
├── local.settings.example.json  # Modelo: copiar para local.settings.json
├── local.settings.json # Local (não versionado — ver .gitignore)
├── .gitignore
└── README.md
```

## Pré-requisitos

- **Python 3.11**
- **Poetry** ([instalação](https://python-poetry.org/docs/#installation))
- **Azure Functions Core Tools v4** ([documentação](https://learn.microsoft.com/azure/azure-functions/functions-run-local))
- Servidor **LiteLLM** (ou outro proxy com API **OpenAI-compatível** em `/v1`) em execução — ver configuração abaixo

## Setup local (Poetry)

Na **raiz** do repositório (onde está o `pyproject.toml`):

```bash
cd maieutica   # ou o caminho onde clonou o repo
poetry install
poetry env activate
```

O ficheiro [`poetry.toml`](poetry.toml) define `virtualenvs.in-project = true`, ou seja, a venv fica em **`.venv/`** nesta pasta (mais estável se mudares de diretório).

### Mudaste a pasta do projeto e a venv “partiu-se”?

O Poetry liga o ambiente virtual ao caminho do projeto. Depois de mover a pasta, recria o ambiente:

```bash
cd /caminho/para/maieutica
poetry env remove --all
rm -rf .venv
poetry install
```

No Cursor/VS Code: **Python: Select Interpreter** → escolhe `.venv/bin/python` (ou `Python 3.11.x ('.venv': poetry)`).

Se usares `func start` noutro terminal, ativa antes a venv: `poetry shell` ou `source .venv/bin/activate`.

Defina as variáveis em **`local.settings.json`** → `Values` (copie a partir de [`local.settings.example.json`](local.settings.example.json)). O `function_app.py` também chama `load_dotenv()`, pelo que um ficheiro **`.env`** na raiz (não versionado) pode ser usado por ferramentas locais, mas a fonte de verdade para `func start` são normalmente as `Values` acima.

| Variável | Descrição |
|----------|-----------|
| `LITELLM_BASE_URL` | **Obrigatória.** URL do proxy (ex.: `http://localhost:4000`). Se não terminar em `/v1`, o código acrescenta automaticamente. |
| `LITELLM_API_KEY` | Chave Bearer esperada pelo proxy (master key / virtual key). Se vazio, tenta `OPENAI_API_KEY`; senão usa o placeholder `litellm` (só para dev sem auth). |
| `LITELLM_MODEL` | Nome do modelo no LiteLLM, conforme o teu `config.yaml`. Padrão: `gpt-4o-mini` — o modelo de produção fixado para a avaliação da dissertação. O modelo efetivamente usado volta em `tutorMeta.model` e no registro de interações. |
| `CLASSIFICADOR_DE_MOVIMENTO` | `regra` (padrão) ou `modelo`: quem classifica o movimento do estudante no degrau em que o texto decide. Qualquer outro valor **derruba o arranque** em vez de cair em `regra` em silêncio — é a chave que a dissertação declara fixa em `regra` na coleta. O valor em vigor volta em `tutorMeta.classificadorDeMovimento`, no registro por turno e no envelope de cada lote de telemetria. |
| `EVALUATION_MODE` | `1`/`true` congela o artefato na configuração avaliada: **sem RAG em qualquer intenção** e sem a ferramenta `suggest_documentation`. Use em bancada e nas sessões em sala. |
| `INTERACTION_LOG_DIR` | Diretório para o registro estruturado por turno (NDJSON, um ficheiro por dia). Vazio desliga a escrita local. |
| `INTERACTION_LOG_TO_BLOB` | `1`/`0` força ou desliga o envio do registro por turno para o Blob Storage. Omitido: segue `TELEMETRY_BLOB_CONNECTION_STRING`. |

As chaves dos provedores (Anthropic, OpenAI, etc.) ficam **no LiteLLM**, não nesta API.

**CORS (browser):** em desenvolvimento local, configure no `local.settings.json` a secção `Host` (ver [`local.settings.example.json`](local.settings.example.json)): `CORS` (por exemplo `*` ou origens separadas por vírgula) e, se precisares de cookies/credenciais, `CORSCredentials`. O runtime do Azure Functions trata os pedidos `OPTIONS` (preflight) com base nisto — **não** é necessário expor `OPTIONS` na função Python. O ficheiro [`host.json`](host.json) **não** define CORS na Azure Functions; em produção, configura CORS no **portal Azure** (Function App → **API** → **CORS**) ou nas **Application settings** do serviço.

Inicie o host local (é necessário ter **Azure Functions Core Tools** (`func`) no `PATH`):

```bash
make start
# ou, com mais detalhe no log:
make dev
```

Equivalente a `func start` / `func start --verbose` na raiz do projeto.

### Modo “watch” (reinício ao editar código)

O Azure Functions Core Tools **não** tem `func start --watch`. Para voltar a levantar o host quando mudas ficheiros `.py`, usa o alvo **`make watch`** (ou `make dev-watch`), que envolve o [`watchfiles`](https://pypi.org/project/watchfiles/):

```bash
make sync    # uma vez, se ainda não instalaste watchfiles (poetry lock + install)
make watch
```

Isto corre `func start --verbose` e **reinicia** o processo quando deteta alterações em ficheiros Python no projeto (é um restart do processo, não hot-reload dentro do mesmo processo).

- **GET** `http://localhost:7071/api/ping` — health check, resposta JSON: `{"pong": true}`.
- **POST** `http://localhost:7071/api/help` — tutor socrático, resposta JSON (`message`, `diagnosis`, `actions`, `tutorMeta`). Preflight CORS é tratado pelo host quando `Host.CORS` está definido em `local.settings.json`.
- **POST** `http://localhost:7071/api/help/stream` — mesmo corpo JSON que `/api/help`, resposta **`text/event-stream`** (SSE). Eventos típicos: `diagnosis` (JSON do analista), `action` (ações pedagógicas na IDE), `token` (fragmentos de texto do tutor), `done` (fim do stream, com `tutorMeta` opcional) ou `error` (falha de validação ou interna). O frontend em [portugol-ai-tutor](https://github.com/luisricar-do/portugol-ai-tutor) consome este endpoint para exibir a resposta em tempo real.
- **POST** `http://localhost:7071/api/help/single` — chamada única ao modelo, sem grafo, para as condições B e C da bancada. Mesmo corpo de `/api/help` mais `promptVariant` (`socratic` | `neutral`); ver [Chamada única para a bancada](#chamada-única-para-a-bancada-post-apihelpsingle).
- **GET** `http://localhost:7071/api/help/single/prompts` — texto e SHA-256 dos dois prompts congelados e do molde de contexto.

## Testes

```bash
make test
```

Equivale a `poetry run pytest`. Argumentos extra: `poetry run pytest -- -k nome_do_teste`.

**Nota:** O Poetry não expõe “scripts” como o `package.json` do Node. Usamos um **Makefile** na raiz. Se alterares dependências no `pyproject.toml`, corre **`make sync`** (`poetry lock && poetry install`) para o `poetry.lock` ficar alinhado — caso contrário o `poetry install` falha.

Os testes unitários **mockam** `agents.llm.ChatOpenAI`; não há chamadas reais ao proxy na suíte padrão.

## Atualizar `requirements.txt` (deploy Azure)

Sempre que alterar dependências de produção no `pyproject.toml`:

```bash
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

> **Poetry 2.x:** se o comando `export` não existir, instale o plugin:  
> `poetry self add poetry-plugin-export`

Em alternativa, mantenha o `requirements.txt` alinhado manualmente com as dependências de produção (como no repositório). O ficheiro na raiz da Function é usado pelo runtime Python na Azure.

## Deploy na Azure (resumo)

1. Crie um **Function App** com runtime **Python 3.11** no portal Azure (ou CLI).
2. Configure **Application settings**: `AzureWebJobsStorage`, `LITELLM_BASE_URL`, `LITELLM_API_KEY` (ou `OPENAI_API_KEY`) e, se necessário, `LITELLM_MODEL`.
3. Configure **CORS** no portal (Function App → **API** → **CORS**) com a origem do frontend (por exemplo `https://portugol.dev`), para o browser conseguir chamar a API em domínio diferente.
4. Faça o deploy a partir da **raiz do repositório** (onde estão `function_app.py` e `host.json`), por exemplo: `func azure functionapp publish <NOME_DO_APP>` com Core Tools autenticado.
5. Garanta que `host.json`, `function_app.py`, `requirements.txt` e os pacotes `agents/` e `services/` entram no pacote publicado.

Consulte a documentação oficial: [Publicar código Python em Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-python).

## API — exemplo de request / response

O corpo JSON abaixo aplica-se tanto a **`POST /api/help`** como a **`POST /api/help/stream`**.

**Request** — `POST /api/help` (ou `/api/help/stream`)

```json
{
  "code": "inteiro i\nenquanto (i < 10) {\n  escreva(i)\n}",
  "errors": ["Aviso: possível loop infinito"],
  "history": [
    {
      "role": "user",
      "content": "Meu programa não termina.",
      "code": "inteiro i\nenquanto (i < 10) {\n}",
      "errors": []
    },
    { "role": "assistant", "content": "Vamos pensar juntos no fluxo do laço." }
  ],
  "sessionId": "sessao-42",
  "previousCode": "inteiro i\nenquanto (i < 10) {\n}",
  "previousErrors": []
}
```

- **`sessionId`** (opcional): identificador de sessão gerado pela IDE, usado como chave do
  registro estruturado. Só `[A-Za-z0-9_-]`, até 64 caracteres. O `studentName` **nunca** entra
  no registro.
- **`previousCode`** / **`previousErrors`** (opcionais): estado do código e erros do compilador
  no turno anterior. Com eles o serviço classifica o **movimento do estudante** (progresso,
  estagnação, regressão, pedido explícito) pela regra objetiva do compilador; sem eles, decide
  pelo texto do último turno.
- **`code`** / **`errors`** dentro de cada turno `user` de **`history`** (opcionais): o estado do
  código e os erros do compilador **naquele** turno. Com eles o serviço reclassifica o histórico
  inteiro e deriva a **estagnação acumulada desde o último progresso**, que é o gatilho do
  escalonamento da dica — o contador sobe a cada turno bloqueado e **zera quando o estudante
  progride**. Turno sem edição repete o estado do turno anterior; enviar só parte dos turnos
  equivale a não enviar nenhum. Sem eles o serviço degrada para o turno corrente, e a resposta
  declara-o em `meta.stagnationSource` (`historico` | `turno` | `nenhum`).
- **`meta.stagnationStreak`** (resposta): o contador que a política consumiu neste turno.

**Response** — `200 OK` (`/api/help`)

```json
{
  "message": "Texto da tutora (uma pergunta socrática, tom acolhedor).",
  "diagnosis": {
    "errorType": "infinite_loop",
    "errorLine": 2,
    "affectedVariable": "i",
    "errorDescription": "...",
    "hintAngle": "...",
    "severity": "high"
  },
  "actions": [],
  "tutorMeta": {
    "suggestedConversationEnd": false,
    "endReason": "none",
    "intent": "DEBUG",
    "studentMovement": "ESTAGNACAO",
    "classificadorDeMovimento": "regra",
    "model": "gpt-4o-mini",
    "usage": {
      "promptTokens": 750,
      "completionTokens": 75,
      "totalTokens": 825,
      "calls": 3
    }
  }
}
```

- **`actions`**: lista de ações de editor (mesmo formato que no SSE `event: action`), por exemplo destaques ou `mark_bug_resolved` quando o problema foi dado como resolvido.
- **`tutorMeta`**: metadados para a UI e para a avaliação. Quando o estrategista emite `mark_bug_resolved`, vem `suggestedConversationEnd: true` e `endReason: "bug_resolved"` — a IDE pode encerrar a conversa atual e abrir uma nova. `intent` é o rótulo do roteador (`DEBUG`, `THEORY`, `CASUAL`, `OUT_OF_SCOPE`), `studentMovement` é o movimento classificado no turno anterior do estudante (`PROGRESSO`, `ESTAGNACAO`, `REGRESSAO`, `PEDIDO_EXPLICITO` ou `NENHUM`; o turno de abertura, que não tem turno anterior, é sempre `NENHUM`) `classificadorDeMovimento` é quem classificou esse movimento (`regra` ou `modelo`, ver a tabela de variáveis) e `model` é o modelo que gerou o turno.
- **`usage`** (só em `/api/help`): soma dos tokens de **todas** as chamadas ao modelo no turno — roteador, analista, estrategista e comunicador —, com `calls` a dizer quantas foram observadas. É esse o custo comparável com a chamada única de `/api/help/single`. O SSE não traz o campo: lá o uso não é recolhido, e zeros permanentes seriam informação falsa.

**Evento SSE `done`** (`/api/help/stream`) — exemplo:

```json
{
  "tutorMeta": {
    "suggestedConversationEnd": false,
    "endReason": "none",
    "intent": "DEBUG",
    "studentMovement": "PROGRESSO",
    "model": "gpt-4o-mini"
  }
}
```

### Registro estruturado por turno

Com `INTERACTION_LOG_DIR` e/ou `INTERACTION_LOG_TO_BLOB` ativos, cada chamada a `/api/help`, a
`/api/help/stream` e a `/api/help/single` grava uma linha NDJSON com o corpo recebido (sem `studentName`), a mensagem
devolvida — no SSE, remontada a partir dos `token` —, o diagnóstico, as ações, o `tutorMeta`, o
movimento classificado, o modelo, a latência e a marca temporal. É desse registro que se derivam
as trajetórias da avaliação. Falha de gravação é registrada no log da aplicação e **não**
interrompe a resposta ao estudante.

**Erros comuns**

- `400` — `code` vazio ou JSON inválido.
- `500` — falha interna (detalhes no log da Function).

## Chamada única para a bancada (`POST /api/help/single`)

Uma única chamada ao modelo, **sem grafo**, para as condições **B** (ablação da arquitetura) e
**C** (referência neutra) da avaliação do Capítulo 4. A condição **A** é o grafo completo, em
`/api/help`. As três saem do mesmo serviço, com o mesmo contrato, o mesmo registro e o mesmo
proxy, para que a comparação não seja confundida por diferença de infraestrutura.

Não corre aqui: roteador, analista, estrategista, comunicador, ferramentas de IDE, RAG e
`suggest_documentation`. Não há memória entre chamadas — todo o contexto vem do corpo do pedido.
Não há pós-processamento nem filtro na saída (o que o modelo responde é o dado da ablação) e
não há recurso ao grafo em caso de falha: erro devolve `500` e o harness reexecuta. Não existe
`/stream` nesta rota — a bancada é síncrona.

**Request** — mesmo corpo de `/api/help`, mais `promptVariant` (obrigatório):

```json
{
  "code": "algoritmo teste\ninicio\n  escreva(x)\nfimalgoritmo",
  "errors": ["Variável não declarada: x"],
  "compilerErrorLines": [3],
  "history": [{ "role": "user", "content": "não entendi o erro" }],
  "hintLevel": 1,
  "sessionId": "bancada-001-b-1",
  "promptVariant": "socratic"
}
```

- **`promptVariant`**: `"socratic"` (condição B) ou `"neutral"` (condição C). Ausente ou
  inválido → `400`.
- O modelo, a temperatura e os demais parâmetros são os do **comunicador** em produção — a fala
  que a condição A entrega ao estudante sai desse mesmo cliente.
- As mensagens são `[system(prompt da variante), user(molde de contexto), *histórico]`. O molde
  de contexto (código numerado, erros do compilador, linhas de erro) usa os rótulos e a ordem do
  grafo; o histórico vai como mensagens de papel `user`/`assistant`, a forma nativa da API de
  chat e a mesma que a condição A usa, de modo que a última mensagem é sempre o turno mais
  recente do estudante. Sem histórico fica só o contexto — não se injeta turno sintético.
- O array é **idêntico** nas duas variantes: entre B e C só muda o prompt de sistema. Nenhuma
  das duas recebe descrição do defeito.
- `hintLevel`, `studentName`, `previousCode` e `previousErrors` são aceitos por compatibilidade
  de contrato, mas **não** entram no prompt. São entradas da política programática — `hintLevel`
  é a saída da decisão do estrategista e os estados anteriores alimentam o classificador de
  movimento; dá-los a B devolveria à ablação a peça que se quer retirar.

**Response** — `200 OK`

```json
{
  "message": "Texto do modelo, sem filtro.",
  "actions": [],
  "tutorMeta": {
    "model": "gpt-4o-mini",
    "promptVariant": "socratic",
    "promptSha256": "eef99ad5…",
    "contextSha256": "e3fd0a7a…",
    "usage": { "promptTokens": 120, "completionTokens": 18, "totalTokens": 138 },
    "finishReason": "stop",
    "latencyMs": 842
  }
}
```

`actions` é sempre vazio e não há `diagnosis`: nenhum componente do grafo corre nesta rota.

`finishReason` vem do modelo. `"length"` marca turno cortado no limite de tokens: em A o
comunicador só traduz um plano interno, enquanto em B a mesma chamada tem de analisar, decidir e
falar — um turno cortado seria classificado com diretividade errada e o viés cairia todo de um
lado da comparação. A bancada reporta a taxa por condição; o limite não é corrigido aqui.

### `GET /api/help/single/prompts`

Devolve o texto e o SHA-256 dos dois prompts congelados e do molde de contexto — material de
reprodutibilidade da dissertação e conferência do harness antes de uma corrida (se algum hash
mudou, a corrida não é comparável com a anterior):

```json
{
  "prompts": {
    "socratic": { "text": "You are ADA, a Socratic programming logic tutor…", "sha256": "eef99ad5…" },
    "neutral": { "text": "Você é um assistente de programação…", "sha256": "53aff9c6…" }
  },
  "context": { "text": "Portugol code with 1-based line numbers:…", "sha256": "e3fd0a7a…" }
}
```

O molde de contexto tem hash próprio porque não é detalhe de implementação: a numeração das
linhas determina o que o modelo consegue citar, logo determina o resultado. `contextSha256`
cobre o molde dessa mensagem, não o array inteiro — o histórico vem do banco de itens.

Os hashes são calculados no arranque do serviço e também registrados no log da aplicação. Os
prompts e o molde são constantes versionadas em `services/tutor_help_single.py`: não são
montados por interpolação nem alterados por variável de ambiente.

O registro NDJSON desta rota é o de `/api/help` (mesmo formato, mesmo destino, `studentName`
nunca gravado), acrescido de `promptVariant`, `promptSha256`, `contextSha256` e `finishReason`.
`EVALUATION_MODE` continua a valer.

## Telemetria da avaliação (`POST /api/telemetry`)

Endpoint de coleta de eventos de uso da IDE (não confundir com o registro por turno acima):
a IDE envia lotes de eventos e cada lote é gravado como um blob NDJSON imutável no Azure Blob
Storage. O campo `condition` é um rótulo livre da etapa de coleta (ex.: `piloto`, `turma-2026-1`);
o desenho de avaliação não tem grupos.

**Configuração** (`local.settings.json` local; App Settings na Azure):

| Variável | Descrição |
| --- | --- |
| `TELEMETRY_BLOB_CONNECTION_STRING` | Connection string da conta de armazenamento. **Vazia desliga a coleta** (o endpoint responde `503` e a IDE mantém os eventos em fila). |
| `TELEMETRY_BLOB_CONTAINER` | Contentor de destino (default: `telemetria`). |

**Request**

```json
{
  "installId": "inst-9f2c...",
  "sessionId": "sess-4a11...",
  "participantId": "P07",
  "condition": "turma-2026-1",
  "buildSha": "abc1234",
  "promptHash": "sha256:...",
  "events": [
    { "seq": 1, "ts": "2026-08-22T10:00:00.000Z", "type": "session_start" },
    { "seq": 2, "ts": "2026-08-22T10:00:09.000Z", "type": "compile", "task": 1, "errorClass": "type_mismatch" }
  ]
}
```

- `installId` / `sessionId`: obrigatórios, até 64 caracteres em `[A-Za-z0-9_-]` (entram no caminho do blob).
- `condition`: rótulo livre da etapa de coleta (ex.: `piloto`, `turma-2026-1`), normalizado para minúsculas e até 64 caracteres. Não é braço experimental — o desenho de avaliação não tem grupos.
- Cada evento exige `type` (string) e `seq` (inteiro ≥ 0); eventos inválidos são descartados e o resto do lote é aceito.
- Máximo de 500 eventos por lote e 1 MiB por lote serializado.
- A identidade (`installId`, `sessionId`, `participantId`, `condition`) é sempre reescrita a partir do envelope, nunca do evento.
- O catálogo de tipos de evento (`task_start`, `code_edit`, `compile`, `chat_turn_user`, …) e os
  respetivos campos estão documentados no README do **portugol-ai-tutor**, em
  *Telemetria da avaliação → Eventos registados*. Este endpoint é agnóstico ao tipo:
  aceita qualquer evento com `type` e `seq`.

**Response** — `200 OK`

```json
{ "accepted": 2, "blob": "sessions/inst-9f2c.../sess-4a11.../000000001-000000002.ndjson" }
```

O nome do blob deriva da faixa de `seq`, logo **repetir o mesmo lote é idempotente**.
Se o cliente reagrupar eventos entre tentativas, pode haver sobreposição entre
blobs — a deduplicação por `(sessionId, seq)` é feita na coleta.

**Erros**

- `400` — JSON inválido, `installId`/`sessionId` ausente ou fora do padrão, `events` vazio.
- `413` — mais de 500 eventos ou lote serializado acima de 1 MiB (o cliente divide e repete).
- `503` — armazenamento não configurado. **O cliente deve manter os eventos e repetir.**
- `500` — falha ao gravar no blob. Idem.

**Baixar os dados**

```bash
export TELEMETRY_BLOB_CONNECTION_STRING="..."
python scripts/fetch_telemetry.py --out dados/
```

Gera `dados/events.ndjson` e `dados/events.csv` (uma linha por evento), remove
duplicados de retentativa e avisa sobre lacunas de `seq` — sinal de perda de
telemetria, relevante para a análise de sensibilidade prevista no protocolo.

## Licença e contexto académico

Projeto de investigação em **Ciência da Computação na Educação**, alinhado a práticas de **Design Science Research** e integração com ecossistema Portugol. Ajuste autores e metadados em `pyproject.toml` conforme a sua dissertação.

## Bancada de avaliação (repositório à parte)

O harness dos Capítulos 4 e 5 — executar o tutor sobre o banco de itens, julgar cada turno com um
juiz automático de família distinta, codificar a subamostra às cegas e apurar H1/H2 — vive em
**[maieutica-avaliacoes](https://github.com/luisricar-do/maieutica-avaliacoes)** (privado: contém
os dados de pesquisa ainda não publicados).

Ficou separado por duas razões. Este repositório é o serviço — Azure Functions, LangGraph,
langchain; a bancada é biblioteca padrão e fala com o serviço só por HTTP, e uma medida que
precisasse de conhecer o interior do que mede não seria medida. E as corridas, os vereditos do
juiz e a codificação humana são **versionados** lá, ao contrário do que acontecia aqui, onde eram
saída de ferramenta no `.gitignore`.

Para correr a avaliação, clone-o ao lado desta pasta e suba o serviço em modo de avaliação
(`EVALUATION_MODE=1` e `INTERACTION_LOG_DIR` no `local.settings.json`):

```bash
make start                    # aqui: o serviço de pé

cd ../maieutica-avaliacoes
make aval-validar
make aval-rodar               # condições A (artefato), B (ablação), C (referência)
make aval-julgar --juiz-protocolo
make aval-analisar
```

As rotas que a bancada consome — `POST /api/help`, `POST /api/help/single` e
`GET /api/help/single/prompts` — estão documentadas acima, e os três prompts são congelados por
SHA-256: se um hash mudar, a corrida anterior deixa de ser comparável e a bancada recusa-se a
fechar a execução.
