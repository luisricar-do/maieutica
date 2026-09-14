# Apuração fechada do Capítulo 5

Scripts de **leitura** sobre a execução `cap4` da bancada. Nada aqui escreve em `avaliacao/`:
nem no banco, nem nos prompts, nem em `execucoes/`. Toda a saída vai para `analise_tese/saida/`
(não versionada). Os 2 020 vereditos e a codificação humana ficam byte a byte como estão.

Sem dependências novas — biblioteca padrão do Python 3.11, como o resto da bancada.

| Script | O que apura |
|---|---|
| `apurar_cap5.py` | Tarefas A–G: composição dos prefixos, concordância bruta e κ, as 19 ocorrências de movimento, os turnos truncados, os de nível 3, a variável `incorreta`, hashes e versão do juiz |
| `detector_referencias.py` | Tarefa H.2: o detector objetivo contra os 160 turnos de referência e as 236 alternativas anotadas do banco |
| `juiz_repeticao.py` | Tarefa H.1: segunda passagem do juiz sobre os mesmos 210 turnos da subamostra, em ficheiro novo |

```bash
python -m analise_tese.apurar_cap5          # → saida/apuracao_cap5.json
python -m analise_tese.detector_referencias # → saida/detector_referencias.json

python -m analise_tese.juiz_repeticao                      # simula: 210 chamadas, tokens, nada é chamado
python -m analise_tese.juiz_repeticao --executar --limite 2 # teste de fumo antes de gastar as 210
python -m analise_tese.juiz_repeticao --executar            # → saida/juizos_repeticao.jsonl
python -m analise_tese.juiz_repeticao --kappa               # → saida/juiz_repeticao_kappa.json
```

`--kappa` devolve duas coisas: o κ do juiz **consigo mesmo** por variável (a estabilidade que o
protocolo exige, no limiar de 0,60) e, como sensibilidade, os κ humano×juiz do Cap. 5
recalculados contra a 2.ª passagem — um κ que só existe numa das passagens não é resultado.

`--executar` recusa-se a correr se o prompt em disco não tiver o hash da corrida
(`5dc2baa3…`) ou se `JUIZ_MODELO` não for o do manifesto (`gemini-3.1-pro-preview`): repetir com
outro prompt ou outro modelo não mede estabilidade do juiz, mede outra coisa. É retomável — o que
já está no ficheiro não é refeito.
