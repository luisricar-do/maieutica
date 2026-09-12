.PHONY: test dev start watch dev-watch lock install sync \
	aval-validar aval-rodar aval-julgar aval-analisar aval-amostra aval-kappa

# Testes (mesmo que `poetry run pytest`)
test:
	poetry run pytest

# Azure Functions local, logs verbosos
dev:
	poetry run func start --verbose

# Azure Functions local
start:
	poetry run func start

# Reinicia o host quando alteras ficheiros .py (o `func` não tem --watch nativo)
watch dev-watch:
	poetry run watchfiles --filter python "poetry run func start --verbose" .

# Regenera poetry.lock quando o pyproject.toml muda
lock:
	poetry lock

install:
	poetry install

# lock + install (útil após editar dependências)
sync:
	poetry lock && poetry install

# ---------------------------------------------------------------- bancada de avaliação
# Ver avaliacao/README.md. Exige o serviço de pé com EVALUATION_MODE=1 e, para julgar,
# GEMINI_API_KEY. Use AVAL="--itens x --execucoes 1" para passar argumentos.

aval-validar:
	python3 -m avaliacao validar $(AVAL)

aval-rodar:
	python3 -m avaliacao rodar $(AVAL)

aval-julgar:
	python3 -m avaliacao julgar $(AVAL)

aval-analisar:
	python3 -m avaliacao analisar $(AVAL)

aval-amostra:
	python3 -m avaliacao amostra-humana $(AVAL)

aval-kappa:
	python3 -m avaliacao kappa $(AVAL)
