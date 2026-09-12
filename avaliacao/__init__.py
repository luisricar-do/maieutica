"""Bancada de avaliação da política de intervenção do tutor (Capítulo 4 da dissertação).

Harness de execução, classificação por juiz automático e análise, tudo por chamadas HTTP:
o artefato responde em ``/api/help``, a referência descritiva vem do mesmo proxy LiteLLM e o
juiz é um modelo de família distinta, acionado por API. Nenhum modelo roda localmente.
"""
