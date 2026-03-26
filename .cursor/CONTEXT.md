# Contexto Cursor — maieutica

## Repositório atual

**maieutica** (nome do pacote Poetry: `portugol-tutor-api`) é a **API do tutor socrático** em Python: Azure Functions + FastAPI extension + **LangGraph** (agente analista → tutor ARIA). Integra com o fork da IDE em [portugol-ai-tutor](https://github.com/luisricar-do/portugol-ai-tutor) via `POST /api/help` e `POST /api/help/stream` (SSE).

- **Raiz da API:** `function_app.py`, `host.json`, `agents/`, `services/`, `tests/`
- **Comandos:** `make test`, `make start` / `make dev`, `make watch` (ver `Makefile`)
- **Dependências:** Poetry (`pyproject.toml`); deploy Azure usa `requirements.txt` exportado
- **Config local:** `local.settings.json` (não versionado); modelo em `local.settings.example.json`
- **LLM:** proxy OpenAI-compatível (`LITELLM_BASE_URL`, etc.) — ver `README.md`

## Projeto companheiro (IDE)

| Repositório        | Caminho típico no disco (ajuste ao teu setup) |
|--------------------|-----------------------------------------------|
| portugol-ai-tutor  | …/mestrado/portugol-ai-tutor                  |

A IDE consome principalmente **`/api/help/stream`** para o chat do tutor.

## Regras neste repo

Ficheiros em `.cursor/rules/*.mdc`:

- **`maieutica-core.mdc`** — contexto do projeto (sempre útil neste workspace)
- **`python-tutor-api.mdc`** — convenções ao editar `*.py`

## Skills Cursor úteis (referência)

Skills globais do utilizador (caminhos em `~/.cursor/skills-cursor/` e plugins):

| Skill / área | Quando usar |
|--------------|-------------|
| `create-rule` | Novas regras `.mdc` ou estrutura `.cursor/rules` |
| `create-skill` | Criar skills personalizadas |
| `update-cursor-settings` | Preferências do editor (`settings.json`) |
| Cursor Team Kit (`check-compiler-errors`, `fix-ci`, `deslop`, etc.) | CI, lint, limpeza de código |
| Prisma skills | **N/A** neste repo (sem Prisma) |
| Figma skills | Só se houver trabalho Figma |

Para usar uma skill: pedir explicitamente à IA ou ela carrega o ficheiro `SKILL.md` quando a tarefa corresponde à descrição da skill.
