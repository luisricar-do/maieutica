# Maieutica

Sistema multiagente (SMA) e instrumentos de pesquisa para a dissertação de mestrado em Ciência e Tecnologia da Computação (UNIFEI — Itajubá).

**Título do trabalho:** *Orquestração de Agentes de IA com Método Socrático para o Ensino de Lógica de Programação: uma integração com o Portugol Webstudio baseada em Design Science Research.*

| | |
| --- | --- |
| Discente | Luis Ricardo Albano Santos |
| Orientador | Prof. Dr. Bruno Guazzelli Batista |
| Programa | PPG em Ciência e Tecnologia da Computação — Itajubá |
| Área / linha | Matemática da Computação · Inteligência Artificial |

## Escopo deste repositório

- **Benchmark de LLMs** (Fase 1 do DSR): prompts com erros típicos em Portugol, rubrica de questioning socrático, avaliação de respostas.
- **Arquitetura do SMA**: orquestrador; agente detector/classificador de erros (sintaxe, lógica, semântica); agente socrático (geração de perguntas sem revelar solução); agente monitor de progresso (scaffolding dinâmico).
- **APIs e serviços** consumidos pela integração no [**portugol-ai-tutor**](https://github.com/luisricar-do/portugol-ai-tutor) (fork do [Portugol Webstudio](https://github.com/dgadelha/Portugol-Webstudio)).

A IDE em si (Angular, worker, parser, etc.) fica no repositório **portugol-ai-tutor**; aqui concentra-se a lógica de IA, orquestração, experimentos e, futuramente, pipelines de dados para Learning Analytics e apoio a instrumentos como NASA-TLX.

## Estrutura prevista (evolutiva)

Os diretórios serão criados conforme o desenvolvimento; planejamento inicial:

- `benchmark/` — conjuntos de prompts, rubricas e scripts de avaliação entre modelos.
- `packages/` ou `services/` — código do SMA (orquestração, chamadas a LLM, políticas socráticas).
- `docs/` — notas de arquitetura e decisões (opcional; evitar duplicar a dissertação).

## Pré-requisitos

- [Node.js](https://nodejs.org/) LTS (alinhar com a versão usada em `portugol-ai-tutor` quando o monorepo for ampliado).
- Chaves de API dos provedores de LLM usados no benchmark e no SMA (veja `.env.example`).

## Configuração

```sh
cp .env.example .env
# edite .env com suas chaves (nunca commite .env)
```

Scripts npm serão adicionados quando os pacotes forem criados.

## Licença

MIT — código original deste repositório. Trechos de terceiros ou datasets com licença própria serão indicados nos respectivos diretórios.

## Referências centrais do plano

Design Science Research (Hevner et al.; Peffers et al.); tutoria socrática com LLMs (Dong et al.); carga cognitiva e ensino de programação para iniciantes (Sweller; Robins; Watson & Li); multiagentes (Wooldridge).
