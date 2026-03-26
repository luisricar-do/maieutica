.PHONY: test dev start watch dev-watch lock install sync

# Testes (mesmo que `poetry run pytest`)
test:
	poetry run pytest

# Azure Functions local, logs verbosos
dev:
	func start --verbose

# Azure Functions local
start:
	func start

# Reinicia o host quando alteras ficheiros .py (o `func` não tem --watch nativo)
watch dev-watch:
	poetry run watchfiles --filter python "func start --verbose" .

# Regenera poetry.lock quando o pyproject.toml muda
lock:
	poetry lock

install:
	poetry install

# lock + install (útil após editar dependências)
sync:
	poetry lock && poetry install
