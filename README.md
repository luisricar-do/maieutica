# Portugol Tutor API

**Repositório:** [github.com/luisricar-do/maieutica](https://github.com/luisricar-do/maieutica)

Backend **multiagente (MAS)** com **tutor socrático** para integração com um fork do **Portugol Webstudio** (portugol.dev), desenvolvido como artefato de dissertação de Mestrado em Informática na Educação (UNIFEI).

O serviço expõe uma **Azure Function** em Python que orquestra dois agentes via **LangGraph**:

1. **Agente Analista** — recebe código Portugol e mensagens de erro do compilador e produz um **diagnóstico estruturado** (JSON).
2. **Agente Tutor Socrático (ARIA)** — recebe o diagnóstico e o histórico da conversa e devolve **apenas orientação por perguntas**, sem entregar a solução pronta.

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
               │ Agente Analista │                                       │  Tutor (ARIA)   │
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
│   ├── tutor.py        # Tutor socrático ARIA
│   ├── llm.py          # Cliente OpenAI-compatível (LiteLLM / proxy)
│   └── graph.py        # Grafo LangGraph (analyst → tutor)
├── services/
│   ├── __init__.py
│   ├── tutor_help.py         # Caso de uso: /api/help (validação + grafo)
│   ├── tutor_help_stream.py  # SSE: /api/help/stream (diagnóstico + tokens)
│   └── ping.py               # Health: resposta JSON para /api/ping
├── tests/
│   ├── test_analyst.py
│   ├── test_tutor.py
│   ├── test_graph.py
│   ├── test_help_service.py
│   ├── test_help_stream.py
│   ├── test_ping.py
│   ├── test_llm.py
│   └── conftest.py
├── function_app.py     # HTTP: /api/ping, /api/help, /api/help/stream
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
| `LITELLM_MODEL` | Nome do modelo no LiteLLM (ex.: `claude-sonnet-4-20250514` ou `anthropic/claude-3-5-sonnet-latest`, conforme o teu `config.yaml`). Padrão: `claude-sonnet-4-20250514`. |

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
- **POST** `http://localhost:7071/api/help` — tutor socrático, resposta JSON única (`message` + `diagnosis`). Preflight CORS é tratado pelo host quando `Host.CORS` está definido em `local.settings.json`.
- **POST** `http://localhost:7071/api/help/stream` — mesmo corpo JSON que `/api/help`, resposta **`text/event-stream`** (SSE). Eventos típicos: `diagnosis` (JSON do analista), `token` (fragmentos de texto do tutor), `done` (fim do stream) ou `error` (falha de validação ou interna). O frontend em [portugol-ai-tutor](https://github.com/luisricar-do/portugol-ai-tutor) consome este endpoint para exibir a resposta em tempo real.

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
    { "role": "user", "content": "Meu programa não termina." },
    { "role": "assistant", "content": "Vamos pensar juntos no fluxo do laço." }
  ]
}
```

**Response** — `200 OK`

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
  }
}
```

**Erros comuns**

- `400` — `code` vazio ou JSON inválido.
- `500` — falha interna (detalhes no log da Function).

## Licença e contexto académico

Projeto de investigação em **Ciência da Computação na Educação**, alinhado a práticas de **Design Science Research** e integração com ecossistema Portugol. Ajuste autores e metadados em `pyproject.toml` conforme a sua dissertação.
