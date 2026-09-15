.PHONY: test dev start watch dev-watch lock install sync

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

# A bancada de avaliação (harness, juiz e apuração dos Caps. 4 e 5) vive em repositório próprio:
# https://github.com/luisricar-do/maieutica-avaliacoes — clonado ao lado desta pasta, os seus
# `make aval-*` e `make apurar-*` correm de lá contra este serviço, por HTTP.
