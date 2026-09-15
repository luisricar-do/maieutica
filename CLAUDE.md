# maieutica (Portugol Tutor API)

API multiagente para **tutor socrático** em Portugol. O tutor **não** entrega solução
pronta — só orientação por perguntas. Pacote Poetry: `portugol-tutor-api`.

## Stack

- Python 3.11, **Azure Functions** (decoradores v2) + FastAPI extension
- **LangGraph** — agente analista → tutor ADA
- `langchain-openai` apontando para proxy **LiteLLM/OpenAI-compatível** (`LITELLM_BASE_URL`, etc.)

## Estrutura e comandos

- **Raiz da API:** `function_app.py`, `host.json`, `agents/`, `services/`, `tests/`
- **Comandos:** `make test` (`pytest`), `make start` / `make dev`, `make watch` (ver `Makefile`)
- **Dependências:** Poetry (`pyproject.toml`); deploy Azure usa `requirements.txt` exportado
- **Config local:** `local.settings.json` (não versionado); ver `local.settings.example.json`

## Bancada de avaliação (repositório à parte)

O harness dos Caps. 4 e 5 vive em **`../maieutica-avaliacoes`**
(https://github.com/luisricar-do/maieutica-avaliacoes, privado). Não trazer nada disso para cá: a
bancada é stdlib e só toca o serviço por HTTP, e é isso que a torna uma medida.

O que isto impõe a mudanças **neste** repositório:

- **Rotas que a bancada consome:** `POST /api/help`, `POST /api/help/single` (`promptVariant`
  `socratic`/`neutral`) e `GET /api/help/single/prompts`. Mudança de contrato aí invalida as
  corridas já feitas — alinhar antes.
- **Prompts congelados:** os três prompts da chamada única têm SHA-256 registrado no manifesto de
  cada execução. Editá-los torna a corrida anterior incomparável; se for deliberado, é execução
  nova, não correção.
- **`agents/movement.py`:** as frases de pressão de H2 e a anotação do banco dependem de
  `is_explicit_request` e `classify_movement`. A guarda que prende a regra às frases está em
  `maieutica-avaliacoes/tests/test_frases_de_pressao.py` — correr aquela suíte depois de mexer no
  padrão, ou H2 passa a medir uma exigência que nunca houve, em silêncio.

## Integração com a IDE (portugol-ai-tutor)

- A IDE (fork em `…/mestrado/portugol-ai-tutor`) consome `POST /api/help` e
  `POST /api/help/stream` (SSE) — principalmente o **stream** para o chat do tutor.
- **Entrada típica:** `code`, `errors`, `history` (JSON). Contratos em `README.md` e
  `services/tutor_help*.py`.
- Novos endpoints ou mudanças de contrato: alinhar com o consumo em
  **portugol-ai-tutor** (`packages/agent`, chat SSE).

## Convenções de código (Python)

- Manter **async** onde o código já é assíncrono; respeitar padrões em `agents/` e `services/`.
- **Grafo LangGraph:** alterações em `agents/graph.py` devem manter o fluxo
  analista → tutor e os tipos de diagnóstico esperados pelo frontend.
- Preferir funções pequenas e nomes alinhados ao domínio (diagnóstico, histórico, stream SSE).
- **Estilo:** Ruff (`pyproject.toml`); `function_app.py` pode ter ignores específicos (`E402`).

## Testes

- `make test` (`pytest`); **LLM mockado** nos testes padrão — não assumir chamadas reais à rede.
- Adicionar/atualizar testes em `tests/`; usar mocks para LLM como nos existentes
  (`conftest.py`, padrões atuais).

## Segurança e deploy

- Nunca commitar `local.settings.json`, `.env` ou chaves. Documentar variáveis no
  arquivo de exemplo, não valores reais.
- **Após mudar deps de produção:** atualizar `requirements.txt` para deploy
  (`poetry export` ou alinhamento manual) conforme `README.md`.
