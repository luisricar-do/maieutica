# Imagem do serviço para Azure Container Apps: o mesmo host do Azure Functions que `make start`
# levanta localmente, com as mesmas rotas (`/api/...`) e o mesmo contrato — só muda onde corre.
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    FUNCTIONS_WORKER_RUNTIME=python \
    PYTHON_ENABLE_INIT_INDEXING=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /
RUN pip install -r /requirements.txt

COPY . /home/site/wwwroot

# Commit da imagem, devolvido por /api/ping: a esteira espera vê-lo para dar o deploy por pronto.
# Por último, para a troca de commit não invalidar a camada do pip.
ARG BUILD_SHA=""
ENV BUILD_SHA=${BUILD_SHA}
