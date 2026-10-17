# Contexto Cursor — maieutica

**maieutica** (pacote Poetry `portugol-tutor-api`) é a **API do tutor socrático** em Python: Azure Functions v2 + FastAPI extension + **LangGraph**, servida em **Azure Container Apps** (imagem em `ghcr.io/luisricar-do/maieutica`). É o artefato medido de uma dissertação de mestrado (UNIFEI). A IDE é o fork [portugol-ai-tutor](https://github.com/luisricar-do/portugol-ai-tutor), que consome principalmente `POST /api/help/stream` (SSE).

**Fonte única: [`CLAUDE.md`](../CLAUDE.md)** (stack, estrutura, comandos, convenções, testes, segurança). Este arquivo não a duplica; em divergência, vale o `CLAUDE.md`. Arquitetura, variáveis e endpoints: `README.md`.

## Invariantes críticas

- **Rotas da bancada:** `POST /api/help`, `POST /api/help/single` e `GET /api/help/single/prompts`. Mudança de contrato invalida as corridas já feitas — alinhar antes.
- **Prompts congelados** (SHA-256 em cada execução; `scripts/hash_prompts.sh`): editar é execução nova, não correção.
- **`agents/movement.py`:** depois de mexer no padrão, correr `maieutica-avaliacoes/tests/test_frases_de_pressao.py`.
- **Histórico da `main` não se reescreve:** a bancada usa `git archive` de `f173f6d` e `1e7e5cd`.
- **Deploy em Container Apps a cada push em `main`**, exceto se só mudarem `README.md`, `CLAUDE.md`, `AGENTS.md` ou `.cursor/**`.

## Repositórios irmãos

| Repositório | Caminho típico no disco (ajuste ao teu setup) |
|-------------|-----------------------------------------------|
| portugol-ai-tutor (IDE) | …/mestrado/portugol-ai-tutor |
| maieutica-avaliacoes (bancada, privada) | …/mestrado/maieutica-avaliacoes |

## Regras neste repo

Ficheiros em `.cursor/rules/*.mdc`:

- **`maieutica-core.mdc`** — contexto e invariantes (sempre ativa)
- **`python-tutor-api.mdc`** — convenções ao editar `*.py`
