# Apuração fechada do Capítulo 5

Scripts de **leitura** sobre a execução `cap4` da bancada. Nada aqui escreve em `avaliacao/`:
nem no banco, nem nos prompts, nem em `execucoes/`. Toda a saída vai para `analise_tese/saida/`
(não versionada). Os 2 020 vereditos e a codificação humana ficam byte a byte como estão.

Sem dependências novas — biblioteca padrão do Python 3.11, como o resto da bancada.

| Script | O que apura |
|---|---|
| `apurar_cap5.py` | Tarefas A–G: composição dos prefixos, concordância bruta e κ, as 19 ocorrências de movimento, os turnos truncados, os de nível 3, a variável `incorreta`, hashes e versão do juiz |
| `detector_referencias.py` | Tarefa H.2: o detector objetivo contra os 160 turnos de referência e as 236 alternativas anotadas do banco |
| `juiz_repeticao.py` | Tarefa H.1: segunda passagem do juiz sobre os mesmos 210 turnos da subamostra, em ficheiro novo, com IC por *bootstrap* e conferência do modelo por chamada; `juiz_repeticao_exec.py` escreve em `saida/<execução>/` |
| `cruzamento_juiz_ciclos.py` | cap4 × cap5 sobre os turnos de referência dos 25 itens do ciclo 1: confere a entrada exacta do juiz nos dois commits, κ entre ciclos (IC por *bootstrap*) sobre os de entrada idêntica, e os pares da linha REF de H1 que viraram |
| `apurar_h1_h2.py` | Tarefas 2–7: contingência **por movimento**, tabela movimento × diretividade, calibração nos 160 turnos de referência, H2 com as sensibilidades de limiar, ablação com latência p95, descritivas por classe de erro, variância entre execuções |
| `preparar_h1_modelo.py` | Junta `h1_turnos.csv` com prioridade, comprimento e edição, e escreve a entrada do modelo |
| `h1_ordinal.R` | Tarefa 1: o modelo ordinal misto de H1 (`ordinal::clmm`) e as sensibilidades inferenciais |
| `metricas_sobreposicao.py` | Tarefa 6: BLEU-4, ROUGE-L e BERTScore multilíngue contra as referências de cada posição |

```bash
python -m analise_tese.apurar_cap5          # → saida/apuracao_cap5.json
python -m analise_tese.detector_referencias # → saida/detector_referencias.json

python -m analise_tese.juiz_repeticao                      # simula: 210 chamadas, tokens, nada é chamado
python -m analise_tese.juiz_repeticao --executar --limite 2 # teste de fumo antes de gastar as 210
python -m analise_tese.juiz_repeticao --executar            # → saida/juizos_repeticao.jsonl
python -m analise_tese.juiz_repeticao --kappa               # → saida/juiz_repeticao_kappa.json

AVALIACAO_EXECUCAO=cap5 python -m analise_tese.juiz_repeticao_exec --executar   # → saida/cap5/juizos_repeticao.jsonl
AVALIACAO_EXECUCAO=cap5 python -m analise_tese.juiz_repeticao_exec --kappa      # → saida/cap5/juiz_repeticao_kappa.json
python -m analise_tese.cruzamento_juiz_ciclos                                    # → saida/cruzamento_cap4_cap5.json
```

`--kappa` devolve duas coisas: o κ do juiz **consigo mesmo** por variável (a estabilidade que o
protocolo exige, no limiar de 0,60) e, como sensibilidade, os κ humano×juiz do Cap. 5
recalculados contra a 2.ª passagem — um κ que só existe numa das passagens não é resultado.

`--executar` recusa-se a correr se o prompt em disco não tiver o hash da corrida
(`5dc2baa3…`) ou se `JUIZ_MODELO` não for o do manifesto (`gemini-3.1-pro-preview`): repetir com
outro prompt ou outro modelo não mede estabilidade do juiz, mede outra coisa. É retomável — o que
já está no ficheiro não é refeito. Antes de começar lista `/v1/models` e recusa se o proxy não
encaminhar o modelo; cada veredito grava `modelo_conferido`, e o `--kappa` conta-os N/N. Os κ
saem com IC a 95% percentílico por *bootstrap* (2 000 reamostras, semente fixa).

## H1, H2, ablação e descritivas

```bash
python -m analise_tese.apurar_h1_h2         # → saida/apuracao_h1_h2.{json,md}
python -m analise_tese.preparar_h1_modelo   # → saida/h1_modelo.csv
Rscript analise_tese/h1_ordinal.R           # → saida/h1_ordinal.{txt,json}
```

O modelo ordinal misto **não** corre no venv da bancada, que é sem dependências por desenho.
Precisa de R com o pacote `ordinal`:

```bash
brew install r
Rscript -e 'install.packages("ordinal", repos="https://cloud.r-project.org")'
```

As métricas de sobreposição precisam de um terceiro ambiente, porque puxam torch:

```bash
python -m venv .venv-metricas
.venv-metricas/bin/pip install sacrebleu rouge-score bert-score
PYTHONPATH=. .venv-metricas/bin/python -m analise_tese.metricas_sobreposicao
```

Duas restrições do desenho que o ajuste declara em vez de contornar: em bancada há um diálogo de
referência por item, logo «diálogo» e «item» são o mesmo fator; e `estagnacao_acumulada` vale 0 se
e só se o movimento é PROGRESSO, logo a interação não é estimável nesse nível. O `h1_ordinal.R`
demonstra as duas antes de reportar o modelo reduzido.
