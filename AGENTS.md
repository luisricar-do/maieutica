# Instruções para agentes (maieutica)

Repositório: **API Portugol Tutor** — Azure Functions v2 + LangGraph (roteador, analista, classificador de movimento, estrategista e comunicador ADA), servida em **Azure Container Apps**. É o artefato medido de uma dissertação de mestrado (UNIFEI).

**Fonte única das instruções: [`CLAUDE.md`](CLAUDE.md).** Este arquivo só orienta e repete as invariantes críticas; em caso de divergência, vale o `CLAUDE.md`.

## Invariantes (resumo — detalhes no CLAUDE.md)

- **Rotas da bancada:** `POST /api/help`, `POST /api/help/single` (`promptVariant` `socratic`/`neutral`) e `GET /api/help/single/prompts`. Mudar o contrato invalida as corridas já feitas — alinhar antes.
- **Prompts congelados:** os três prompts da chamada única têm SHA-256 registrado em cada execução (`scripts/hash_prompts.sh` cobre o pacote do grafo). Editá-los torna a corrida anterior incomparável: é execução nova, não correção.
- **`agents/movement.py`:** as frases de pressão de H2 dependem de `is_explicit_request` e `classify_movement`. Depois de mexer no padrão, correr `maieutica-avaliacoes/tests/test_frases_de_pressao.py`.
- **Não reescrever o histórico:** a bancada reconstrói corridas por `git archive` dos commits `f173f6d` e `1e7e5cd`. Nada de rebase, squash ou `push --force` na `main`.
- **Deploy:** todo push em `main` dispara a esteira (pytest → GHCR → Container Apps) e vai para produção, **exceto** quando só mudam `README.md`, `CLAUDE.md`, `AGENTS.md` e `.cursor/**` (`paths-ignore` em `.github/workflows/deploy-containerapp.yml`).

## Onde ler mais

- **`CLAUDE.md`** — stack, convenções, testes, segurança e as invariantes completas.
- **`README.md`** — arquitetura, variáveis de ambiente, endpoints, deploy e contexto acadêmico.
- **`.cursor/CONTEXT.md`** e **`.cursor/rules/*.mdc`** — versão resumida para o Cursor.

## Comandos rápidos

- Testes: `make test`
- Servidor local: `make start` ou `make dev`
- Reload ao editar: `make watch` (com `watchfiles` instalado)

Responde em **português** quando o utilizador pedir.
