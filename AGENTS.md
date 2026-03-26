# Instruções para agentes (maieutica)

Repositório: **API Portugol Tutor** — Azure Functions + LangGraph (analista + tutor socrático ARIA).

## Onde ler contexto detalhado

- **`.cursor/CONTEXT.md`** — visão do projeto, repo companheiro (IDE), índice de rules e skills.
- **`README.md`** — arquitetura, variáveis de ambiente, endpoints `/api/ping`, `/api/help`, `/api/help/stream`.

## Regras automáticas

Ficheiros em **`.cursor/rules/*.mdc`** (core do projeto + convenções para `*.py`).

## Comandos rápidos

- Testes: `make test`
- Servidor local: `make start` ou `make dev`
- Reload ao editar: `make watch` (com `watchfiles` instalado)

Responde em **português** quando o utilizador pedir.
