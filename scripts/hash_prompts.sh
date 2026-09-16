#!/usr/bin/env bash
# Hash SHA-256 do pacote de prompts do grafo.
#
# Os prompts do artefato vivem no código, e não em arquivos de texto: o template do
# estrategista é uma constante em `agents/strategist.py`, e o mesmo vale para os outros
# quatro agentes. Por isso o pacote é o conjunto desses cinco arquivos, nesta ordem, e o
# hash do pacote é o SHA-256 da concatenação dos seus bytes.
#
# Existe porque o manifesto de cada corrida grava o commit do artefato, mas não um hash dos
# prompts do grafo — só dos prompts do juiz e das duas condições de chamada única. Sem este
# script, conferir que um apêndice descreve o prompt que uma corrida usou obriga a ler o
# diff do commit. Com ele, compara-se um número.
#
#   ./scripts/hash_prompts.sh              # árvore de trabalho
#   ./scripts/hash_prompts.sh f173f6d      # um commit qualquer
#
# A ordem é parte da definição: mudá-la muda o hash do pacote sem mudar prompt nenhum.

set -euo pipefail

ARQUIVOS=(
  agents/router.py
  agents/analyst.py
  agents/strategist.py
  agents/tutor.py
  agents/graph.py
)

COMMIT="${1:-}"

soma() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | cut -d' ' -f1
  else
    shasum -a 256 | cut -d' ' -f1
  fi
}

conteudo() {
  if [ -n "$COMMIT" ]; then
    git show "$COMMIT:$1"
  else
    cat "$1"
  fi
}

if [ -n "$COMMIT" ]; then
  echo "commit: $(git rev-parse "$COMMIT")"
else
  echo "árvore de trabalho ($(git rev-parse --short HEAD), $(git status --porcelain | wc -l | tr -d ' ') arquivos modificados)"
fi
echo

for arquivo in "${ARQUIVOS[@]}"; do
  printf '%-24s %s\n' "$arquivo" "$(conteudo "$arquivo" | soma)"
done

echo
PACOTE=$(for arquivo in "${ARQUIVOS[@]}"; do conteudo "$arquivo"; done | soma)
printf '%-24s %s\n' 'pacote' "$PACOTE"
