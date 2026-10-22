#!/usr/bin/env bash
# Provisiona o maieutica em Azure Container Apps e liga a esteira do GitHub
# (.github/workflows/deploy-containerapp.yml). Idempotente: correr de novo só acerta o que mudou.
#
# Cria, dentro do resource group já existente:
#   - Log Analytics (logs do Container Apps)
#   - Storage Account + contentor `telemetria` (telemetria da IDE e registro por turno),
#     com soft delete de blobs: são os dados da coleta.
#   - Container Apps Environment + Container App (ingress público, porta 80, CORS)
#   - Identidade gerida com credencial federada para o GitHub Actions (OIDC, sem segredo)
#     e papel Contributor no RG; grava as variables AZURE_* no repositório.
#
# O LiteLLM não é provisionado: o serviço usa o proxy já existente (LITELLM_BASE_URL).
#
# Pré-requisitos: `az login` na assinatura certa (Owner ou User Access Administrator no RG,
# para a atribuição de papel), `gh auth login` com acesso de admin ao repositório.
#
# Uso:
#   LITELLM_BASE_URL=https://... LITELLM_API_KEY=sk-... ./scripts/azure_setup.sh
#
# Opcionais (com padrão):
#   CORS_ORIGINS   origens da IDE, separadas por espaço   ("*")
#   MIN_REPLICAS   0 = escala a zero (arranque a frio)    (0)   — usar 1 durante as aulas
#   MAX_REPLICAS                                          (3)
#   GHCR_PAT       PAT clássico com read:packages; só se o pacote no GHCR ficar privado
#   STUDY_ADMIN_TOKEN  token do painel do condutor (/api/painel); sem ele o painel responde 503
set -euo pipefail

: "${LITELLM_BASE_URL:?defina LITELLM_BASE_URL}"
: "${LITELLM_API_KEY:?defina LITELLM_API_KEY}"

RG="${RG:-dev-maieutica-rg}"
LOG_NAME="${LOG_NAME:-dev-maieutica-log}"
ENV_NAME="${ENV_NAME:-dev-maieutica-cae}"
APP_NAME="${APP_NAME:-dev-maieutica-ca}"
IDENTITY_NAME="${IDENTITY_NAME:-dev-maieutica-github-id}"
BLOB_CONTAINER="${BLOB_CONTAINER:-telemetria}"
GH_REPO="${GH_REPO:-luisricar-do/maieutica}"
GH_BRANCH="${GH_BRANCH:-main}"

LITELLM_MODEL="${LITELLM_MODEL:-gpt-4o-mini}"
LITELLM_EMBEDDING_MODEL="${LITELLM_EMBEDDING_MODEL:-azure/text-embedding-3-small}"
CORS_ORIGINS="${CORS_ORIGINS:-*}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"
MAX_REPLICAS="${MAX_REPLICAS:-3}"

# Imagem provisória só na criação; a esteira troca-a pela do GHCR no primeiro deploy.
PLACEHOLDER_IMAGE="mcr.microsoft.com/k8se/quickstart:latest"

log() { printf '\n==> %s\n' "$*"; }

# SHA-1 em hex: `sha1sum` no Linux/Cloud Shell, `shasum` no macOS — mesmo resultado nos dois.
sha1_hex() {
  if command -v sha1sum >/dev/null 2>&1; then sha1sum; else shasum; fi | cut -d' ' -f1
}

log "Assinatura e resource group"
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
az account show --query "{assinatura:name, id:id}" -o table
LOCATION=$(az group show -n "$RG" --query location -o tsv) \
  || { echo "Resource group $RG não existe nesta assinatura." >&2; exit 1; }
echo "RG $RG em $LOCATION"

# Nome de storage é global, 3–24 minúsculas/dígitos: sufixo estável derivado da assinatura.
STORAGE_NAME="${STORAGE_NAME:-devmaieutica$(printf '%s' "$SUBSCRIPTION_ID" | sha1_hex | cut -c1-8)}"

log "Extensão containerapp e resource providers"
az extension add --name containerapp --upgrade --yes --only-show-errors
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.Storage Microsoft.ManagedIdentity; do
  az provider register --namespace "$ns" --wait -o none
done

log "Log Analytics ($LOG_NAME)"
az monitor log-analytics workspace create -g "$RG" -n "$LOG_NAME" -l "$LOCATION" -o none
LOG_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LOG_NAME" --query customerId -o tsv)
LOG_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LOG_NAME" \
  --query primarySharedKey -o tsv)

log "Storage ($STORAGE_NAME / $BLOB_CONTAINER)"
if ! az storage account show -g "$RG" -n "$STORAGE_NAME" -o none 2>/dev/null; then
  az storage account create -g "$RG" -n "$STORAGE_NAME" -l "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 \
    --min-tls-version TLS1_2 --allow-blob-public-access false -o none
fi
az storage account blob-service-properties update -g "$RG" -n "$STORAGE_NAME" \
  --enable-delete-retention true --delete-retention-days 30 \
  --enable-container-delete-retention true --container-delete-retention-days 30 -o none
BLOB_CONN=$(az storage account show-connection-string -g "$RG" -n "$STORAGE_NAME" \
  --query connectionString -o tsv)
az storage container create --name "$BLOB_CONTAINER" --connection-string "$BLOB_CONN" -o none

log "Container Apps Environment ($ENV_NAME)"
if ! az containerapp env show -g "$RG" -n "$ENV_NAME" -o none 2>/dev/null; then
  az containerapp env create -g "$RG" -n "$ENV_NAME" -l "$LOCATION" \
    --logs-workspace-id "$LOG_ID" --logs-workspace-key "$LOG_KEY" -o none
fi

# EVALUATION_MODE=1 e CLASSIFICADOR_DE_MOVIMENTO=regra: a configuração que a dissertação avalia
# (sem RAG; classificador pré-registado). Mudar aqui muda o que a coleta mede.
SECRETS=(
  "litellm-api-key=$LITELLM_API_KEY"
  "blob-connection-string=$BLOB_CONN"
)
ENV_VARS=(
  "LITELLM_BASE_URL=$LITELLM_BASE_URL"
  "LITELLM_API_KEY=secretref:litellm-api-key"
  "LITELLM_MODEL=$LITELLM_MODEL"
  "LITELLM_EMBEDDING_MODEL=$LITELLM_EMBEDDING_MODEL"
  "AzureWebJobsStorage=secretref:blob-connection-string"
  "TELEMETRY_BLOB_CONNECTION_STRING=secretref:blob-connection-string"
  "TELEMETRY_BLOB_CONTAINER=$BLOB_CONTAINER"
  "INTERACTION_LOG_TO_BLOB=1"
  "EVALUATION_MODE=1"
  "CLASSIFICADOR_DE_MOVIMENTO=regra"
)
# Painel do condutor: o token vai como segredo; sem ele as rotas /api/painel/* ficam em 503.
if [[ -n "${STUDY_ADMIN_TOKEN:-}" ]]; then
  SECRETS+=("study-admin-token=$STUDY_ADMIN_TOKEN")
  ENV_VARS+=("STUDY_ADMIN_TOKEN=secretref:study-admin-token")
fi

log "Container App ($APP_NAME)"
if ! az containerapp show -g "$RG" -n "$APP_NAME" -o none 2>/dev/null; then
  az containerapp create -g "$RG" -n "$APP_NAME" --environment "$ENV_NAME" \
    --image "$PLACEHOLDER_IMAGE" \
    --ingress external --target-port 80 --transport auto \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" \
    --secrets "${SECRETS[@]}" \
    --env-vars "${ENV_VARS[@]}" \
    -o none
else
  az containerapp secret set -g "$RG" -n "$APP_NAME" --secrets "${SECRETS[@]}" -o none
  az containerapp update -g "$RG" -n "$APP_NAME" \
    --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" \
    --set-env-vars "${ENV_VARS[@]}" \
    -o none
fi

# O CORS do `local.settings.json` só vale no `func start`; no container quem responde ao
# preflight é o ingress do Container Apps. Headers listados um a um: com `*` o ingress devolve
# 403 ao preflight que pede `content-type`, e a IDE pede-o em toda chamada.
log "CORS ($CORS_ORIGINS)"
read -r -a ORIGINS <<< "$CORS_ORIGINS"
az containerapp ingress cors enable -g "$RG" -n "$APP_NAME" \
  --allowed-origins "${ORIGINS[@]}" \
  --allowed-methods GET POST OPTIONS \
  --allowed-headers content-type accept -o none

if [[ -n "${GHCR_PAT:-}" ]]; then
  log "Credencial do GHCR (pacote privado)"
  az containerapp registry set -g "$RG" -n "$APP_NAME" \
    --server ghcr.io --username "${GH_REPO%%/*}" --password "$GHCR_PAT" -o none
fi

log "Identidade do GitHub Actions ($IDENTITY_NAME)"
az identity create -g "$RG" -n "$IDENTITY_NAME" -l "$LOCATION" -o none
CLIENT_ID=$(az identity show -g "$RG" -n "$IDENTITY_NAME" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -g "$RG" -n "$IDENTITY_NAME" --query principalId -o tsv)
FED_NAME="github-${GH_BRANCH}"
if ! az identity federated-credential show -g "$RG" --identity-name "$IDENTITY_NAME" \
     -n "$FED_NAME" -o none 2>/dev/null; then
  az identity federated-credential create -g "$RG" --identity-name "$IDENTITY_NAME" \
    -n "$FED_NAME" \
    --issuer "https://token.actions.githubusercontent.com" \
    --subject "repo:${GH_REPO}:ref:refs/heads/${GH_BRANCH}" \
    --audiences "api://AzureADTokenExchange" -o none
fi
RG_ID=$(az group show -n "$RG" --query id -o tsv)
if [[ -z "$(az role assignment list --assignee "$PRINCIPAL_ID" --scope "$RG_ID" \
      --role Contributor --query '[].id' -o tsv)" ]]; then
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role Contributor --scope "$RG_ID" -o none
fi

log "Variables do repositório $GH_REPO"
gh variable set AZURE_CLIENT_ID         -R "$GH_REPO" -b "$CLIENT_ID"
gh variable set AZURE_TENANT_ID         -R "$GH_REPO" -b "$TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID   -R "$GH_REPO" -b "$SUBSCRIPTION_ID"
gh variable set AZURE_RESOURCE_GROUP    -R "$GH_REPO" -b "$RG"
gh variable set AZURE_CONTAINERAPP_NAME -R "$GH_REPO" -b "$APP_NAME"

FQDN=$(az containerapp show -g "$RG" -n "$APP_NAME" \
  --query properties.configuration.ingress.fqdn -o tsv)
cat <<EOF

Pronto.
  API:      https://${FQDN}/api   (ainda com a imagem provisória)
  Storage:  ${STORAGE_NAME} / ${BLOB_CONTAINER}

Próximos passos:
  1. gh workflow run deploy-containerapp.yml -R ${GH_REPO}   (ou push na ${GH_BRANCH})
  2. Na primeira publicação, o pacote ghcr.io/${GH_REPO} nasce privado: torná-lo público em
     github.com/${GH_REPO%%/*}?tab=packages → maieutica → Package settings → Change visibility,
     ou correr este script de novo com GHCR_PAT=<PAT com read:packages>. Depois, re-run do job deploy.
  3. Apontar a IDE (portugol-ai-tutor) para https://${FQDN}/api
EOF
