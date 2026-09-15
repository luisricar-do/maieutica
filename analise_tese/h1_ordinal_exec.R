# Modelo ordinal misto de H1, por execução (Subseção 4.3.5 / «Plano analítico» da metodologia).
#
# Mesma especificação de `analise_tese/h1_ordinal.R`; o que muda é só o endereçamento:
#   entrada  saida/<AVALIACAO_EXECUCAO>/h1_modelo.csv
#   saída    saida/<AVALIACAO_EXECUCAO>/h1_ordinal.txt e .json
# para não colidir com a fenda única `saida/h1_modelo.csv`, que `poder_h1_corpus.R` lê como
# sendo o ciclo 1.
#
# Acrescenta ao original: as sensibilidades declaradas no plano analítico do Cap. 4 corridas
# **todas**, cada uma nomeada e com o seu n, com a de ORIGEM imediatamente a seguir ao ajuste
# principal; e o registo explícito de convergência, pacote e simplificação da estrutura aleatória.
#
#   AVALIACAO_EXECUCAO=cap5 Rscript analise_tese/h1_ordinal_exec.R

suppressPackageStartupMessages(library(ordinal))

exec <- Sys.getenv("AVALIACAO_EXECUCAO", "cap4")
raiz <- dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1]))
if (is.na(raiz) || raiz == "") raiz <- "analise_tese"
source(file.path(raiz, "ressalva_prioridade.R"))
saida <- file.path(raiz, "saida", exec)
dados <- read.csv(file.path(saida, "h1_modelo.csv"), stringsAsFactors = FALSE)

dados$diretividade <- factor(dados$diretividade, levels = 0:3, ordered = TRUE)
dados$movimento <- relevel(factor(dados$movimento), ref = "ESTAGNACAO")
dados$item_id <- factor(dados$item_id)
dados$prefixo_id <- factor(dados$prefixo_id)
dados$dialogo_id <- factor(dados$dialogo_id)
dados$comprimento_c <- as.numeric(scale(dados$comprimento, center = TRUE, scale = FALSE)) / 100

linhas <- character()
di <- function(...) linhas <<- c(linhas, sprintf(...))

di("EXECUÇÃO: %s", exec)
di("Pacote: ordinal %s (R %s) · clmm · ligação logit · aproximação de Laplace · Hess = TRUE",
   as.character(packageVersion("ordinal")), paste0(R.version$major, ".", R.version$minor))
di("")
di("Turnos elegíveis: %d (condição A, prefixos de referência, k >= 2, sem pedido explícito).", nrow(dados))
di("Itens: %d · diálogos: %d · prefixos: %d · execuções por prefixo: %d",
   nlevels(dados$item_id), nlevels(dados$dialogo_id), nlevels(dados$prefixo_id),
   max(table(dados$prefixo_id)))
di("")
di("EXCLUSÕES A MONTANTE (o que não está nas %d linhas):", nrow(dados))
di("  · condições B e C — não têm política de contingência a testar;")
di("  · prefixos de pressão — movimento PEDIDO_EXPLICITO, população de H2;")
di("  · turnos de abertura k = 1, movimento NENHUM — não há turno anterior;")
di("  · turnos com falha técnica — contados no relatório de sensibilidade abaixo.")
di("")
di("Confundimento estrutural entre movimento e acumulado:")
tab <- table(dados$movimento, dados$estagnacao_acumulada)
linhas <<- c(linhas, capture.output(print(tab)), "")
di("PROGRESSO só ocorre com acumulado 0; ESTAGNACAO e REGRESSAO só com acumulado >= 1.")
di("Logo a interação não é estimável no nível PROGRESSO, e o efeito do acúmulo lê-se no")
di("subconjunto bloqueado. Não é escolha de ajuste: é a definição do regressor.")
di("")

registo <- list()

ajustar <- function(formula, dd, rotulo, chave = NULL) {
  di("========================================================================")
  di("%s", rotulo)
  di("  n = %d · prefixos = %d · itens = %d",
     nrow(dd), length(unique(as.character(dd$prefixo_id))), length(unique(as.character(dd$item_id))))
  di("  fórmula: %s", paste(deparse(formula), collapse = ""))
  avisos <- character()
  ajuste <- withCallingHandlers(
    tryCatch(clmm(formula, data = dd, Hess = TRUE, link = "logit"),
             error = function(e) { di("  NÃO CONVERGE (erro): %s", conditionMessage(e)); NULL }),
    warning = function(w) { avisos <<- c(avisos, conditionMessage(w)); invokeRestart("muffleWarning") })
  for (a in avisos) di("  AVISO: %s", a)
  if (is.null(ajuste)) { di(""); return(NULL) }
  co <- coef(summary(ajuste))
  fixos <- co[!grepl("\\|", rownames(co)), , drop = FALSE]
  ic <- cbind(fixos[, 1] - 1.96 * fixos[, 2], fixos[, 1] + 1.96 * fixos[, 2])
  di("  %-36s %9s %8s %9s %9s %9s", "efeito", "coef", "EP", "IC inf", "IC sup", "p")
  for (i in seq_len(nrow(fixos))) {
    di("  %-36s %9.3f %8.3f %9.3f %9.3f %9.4f",
       rownames(fixos)[i], fixos[i, 1], fixos[i, 2], ic[i, 1], ic[i, 2], fixos[i, 4])
  }
  va <- tryCatch(VarCorr(ajuste), error = function(e) NULL)
  singulares <- character()
  if (!is.null(va)) {
    for (g in names(va)) {
      v <- as.numeric(va[[g]])[1]
      if (v < 1e-6) singulares <- c(singulares, g)
      di("  variância aleatória %-24s %9.4f %s", g, v,
         ifelse(v < 1e-6, "(singular — o fator não separa nada)", ""))
    }
  }
  conv <- ajuste$optRes$convergence
  di("  logLik = %.2f · AIC = %.2f · convergência: %s",
     as.numeric(logLik(ajuste)), AIC(ajuste),
     ifelse(conv == 0, "sim (código 0)", paste("NÃO — código", conv)))
  di("")
  if (!is.null(chave)) {
    registo[[chave]] <<- list(n = nrow(dd), convergiu = (conv == 0),
                              singulares = singulares, coefs = fixos)
  }
  ajuste
}

linha_de <- function(aj, termo) {
  if (is.null(aj)) return(NULL)
  co <- coef(summary(aj))
  if (!termo %in% rownames(co)) return(NULL)
  co[termo, ]
}
fmt <- function(v) if (is.null(v)) "—" else
  sprintf("%.3f (EP %.3f) [%.3f; %.3f] p = %.4f", v[1], v[2], v[1] - 1.96 * v[2], v[1] + 1.96 * v[2], v[4])

# =============================================================== AJUSTES PRINCIPAIS
m0 <- ajustar(diretividade ~ movimento * estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
              dados, "AJUSTE 0 — especificação declarada (item = diálogo em bancada)", "ajuste0")
if (!is.null(m0)) {
  aliasado <- rownames(coef(summary(m0)))[is.na(coef(summary(m0))[, 2])]
  di("Termos não estimáveis no ajuste 0: %s",
     ifelse(length(aliasado) == 0, "nenhum sinalizado pelo R", paste(aliasado, collapse = ", ")))
  di("")
}

m0b <- ajustar(diretividade ~ movimento * estagnacao_acumulada + k
                 + (1 | item_id) + (1 | dialogo_id) + (1 | prefixo_id),
               dados, "AJUSTE 0b — «diálogo» e «item» a par, como a especificação os lista", "ajuste0b")
di("SIMPLIFICAÇÃO DA ESTRUTURA ALEATÓRIA, declarada: a especificação do Cap. 4 pede (1|item) +")
di("(1|diálogo) + execuções aninhadas no prefixo. Em bancada há **um** diálogo de referência por")
di("item: os dois fatores têm os mesmos %d níveis, a variância reparte-se arbitrariamente entre", nlevels(dados$item_id))
di("eles e o modelo não os identifica em separado. A estrutura reportada é (1|item) + (1|prefixo).")
di("É imposição do desenho da bancada, não escolha de ajuste, e em uso real não se aplica —")
di("lá a trajetória substitui o diálogo e os dois fatores separam-se.")
di("")

bloqueados <- droplevels(subset(dados, movimento %in% c("ESTAGNACAO", "REGRESSAO")))
m1 <- ajustar(diretividade ~ movimento * estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
              bloqueados, "AJUSTE 1 — efeito do acúmulo, só turnos bloqueados", "ajuste1")
m1b <- ajustar(diretividade ~ movimento + estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
               bloqueados, "AJUSTE 1b — idem, sem interação (é este que o critério de H1 lê)", "ajuste1b")
m2 <- ajustar(diretividade ~ movimento + k + (1 | item_id) + (1 | prefixo_id),
              dados, "AJUSTE 2 — efeito do movimento sobre todos os elegíveis (ref.: ESTAGNACAO)", "ajuste2")

# =============================================================== SENSIBILIDADES
di("########################################################################")
di("SENSIBILIDADES DECLARADAS NO PLANO ANALÍTICO (Cap. 4, parágrafo «Sensibilidade»)")
di("########################################################################")
di("")

# --- 1. ORIGEM — obrigatória, e vem primeiro ---------------------------------------------------
di("### SENSIBILIDADE 1 — ORIGEM (cada origem do banco, separadamente)")
di("No ciclo 1 o coeficiente do acúmulo divergiu por origem: -0,975 em `tese` contra +0,579 em")
di("`al_hossami_v2`. Com 26 dos 45 itens escritos pelo autor, esta é a checagem que decide se um")
di("eventual efeito vive no corpus construído ou no corpus derivado de diálogos reais.")
di("")
por_origem <- list()
for (o in sort(unique(dados$origem))) {
  aj <- ajustar(diretividade ~ movimento + estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
                droplevels(subset(bloqueados, origem == o)),
                sprintf("SENSIBILIDADE 1 — acúmulo, só origem `%s`", o), paste0("origem_", o))
  por_origem[[o]] <- linha_de(aj, "estagnacao_acumulada")
  ajustar(diretividade ~ movimento + k + (1 | item_id) + (1 | prefixo_id),
          droplevels(subset(dados, origem == o)),
          sprintf("SENSIBILIDADE 1 — movimento, só origem `%s`", o), paste0("origem_mov_", o))
}
di("--- Acúmulo por origem, lado a lado ---")
for (o in names(por_origem)) di("  %-16s %s", o, fmt(por_origem[[o]]))
di("  conjunto         %s", fmt(linha_de(m1b, "estagnacao_acumulada")))
di("")

# --- 2. Prioridade ------------------------------------------------------------------------------
# Este é o único ajuste do conjunto que dá p < 0,05, e por isso é o número mais perigoso do
# relatório: sozinho numa tabela, lê-se como apoio a H1. Não é. A ressalva abaixo é construída a
# partir dos dados — não é texto fixo — e acompanha o valor em TODOS os artefatos gerados (.txt,
# .json, .csv e .tex). `analise_tese/conferir_ciclos.py` reprova se o valor aparecer sem ela.
di("### SENSIBILIDADE 2 — excluindo os itens de menor prioridade (prioridade 3)")
s2a <- ajustar(diretividade ~ movimento + estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
               droplevels(subset(bloqueados, prioridade != 3)),
               "SENSIBILIDADE 2 — acúmulo, sem prioridade 3", "prioridade_acumulo")
RESSALVA <- ressalva_prioridade(bloqueados, linha_de(s2a, "estagnacao_acumulada")[4])
di("  RESSALVA OBRIGATORIA (acompanha este valor em todos os artefatos):")
for (pedaco in strwrap(RESSALVA, width = 100)) di("    %s", pedaco)
di("")
s2b <- ajustar(diretividade ~ movimento + k + (1 | item_id) + (1 | prefixo_id),
               droplevels(subset(dados, prioridade != 3)),
               "SENSIBILIDADE 2 — movimento, sem prioridade 3", "prioridade_movimento")

# --- 3. Falhas técnicas --------------------------------------------------------------------------
di("### SENSIBILIDADE 3 — excluindo as falhas técnicas")
di("`falha_tecnica` é filtrada a montante, em `apurar_h1_h2`/`analisar`; o que chega aqui já não")
di("as tem. O número que dá conteúdo a esta sensibilidade é a contagem na corrida, e sai do")
di("script Python `h1_h2_sensibilidades_exec.py` (coluna `falha_tecnica` de `turnos_julgados`).")
di("Se a contagem for zero, a sensibilidade é vazia por construção e é isso que se reporta —")
di("não é uma análise que confirma, é uma análise que não tem do que ser retirada.")
di("")

# --- 4/5. Limiares de H2 -------------------------------------------------------------------------
di("### SENSIBILIDADES 4 e 5 — limiares de H2 a 5%% e 15%%")
di("H2 é proporção com IC de Wilson, não modelo ordinal: corre em `h1_h2_sensibilidades_exec.py`.")
di("")

# --- 6. Associação comprimento × diretividade ------------------------------------------------------
di("### SENSIBILIDADE 6 — associação entre o comprimento do turno e a diretividade")
di("Spearman sobre os turnos elegíveis, e por condição, em `h1_h2_sensibilidades_exec.py`.")
di("Aqui fica a leitura dentro do modelo: a diretividade média por nível e o comprimento médio.")
cm <- aggregate(comprimento ~ diretividade, data = dados, FUN = function(x) c(n = length(x), media = mean(x)))
for (i in seq_len(nrow(cm))) {
  di("  diretividade %s: n = %d · comprimento médio = %.1f caracteres",
     as.character(cm$diretividade[i]), cm$comprimento[i, "n"], cm$comprimento[i, "media"])
}
di("")

# --- 7. Comprimento como covariável ---------------------------------------------------------------
di("### SENSIBILIDADE 7 — H1 repetida com o comprimento como covariável")
s7a <- ajustar(diretividade ~ movimento + estagnacao_acumulada + k + comprimento_c + (1 | item_id) + (1 | prefixo_id),
               bloqueados, "SENSIBILIDADE 7 — acúmulo com comprimento (centrado, /100) como covariável",
               "comprimento_acumulo")
s7b <- ajustar(diretividade ~ movimento + k + comprimento_c + (1 | item_id) + (1 | prefixo_id),
               dados, "SENSIBILIDADE 7 — movimento com comprimento como covariável", "comprimento_movimento")

# --- extra do ciclo 1, mantida para comparabilidade -------------------------------------------------
di("### EXTRA (não é das sete; vem de `h1_ordinal.R` do ciclo 1 e fica para comparabilidade)")
com_edicao <- droplevels(subset(dados, houve_edicao == "True"))
ajustar(diretividade ~ movimento + k + (1 | item_id),
        com_edicao,
        sprintf("EXTRA — subamostra com edição de código (n=%d): variável independente vinda dos casos de teste",
                nrow(com_edicao)), "com_edicao")

# =============================================================== VEREDITO
di("========================================================================")
di("VEREDITO DE H1 — critério do Cap. 4, inalterado: acúmulo positivo a 5%% E progresso não positivo")
criterio_acumulo <- NA; p_acumulo <- NA; coef_acumulo <- NA; ep_acumulo <- NA
v <- linha_de(m1b, "estagnacao_acumulada")
if (!is.null(v)) {
  coef_acumulo <- v[1]; ep_acumulo <- v[2]; p_acumulo <- v[4]
  criterio_acumulo <- (coef_acumulo > 0) && (p_acumulo < 0.05)
}
criterio_progresso <- NA; p_progresso <- NA; coef_progresso <- NA; ep_progresso <- NA
v <- linha_de(m2, "movimentoPROGRESSO")
if (!is.null(v)) {
  coef_progresso <- v[1]; ep_progresso <- v[2]; p_progresso <- v[4]
  criterio_progresso <- !((coef_progresso > 0) && (p_progresso < 0.05))
}
di("  acúmulo positivo a 5%%: coef = %.3f (EP %.3f) [%.3f; %.3f], p = %.4f → %s",
   coef_acumulo, ep_acumulo, coef_acumulo - 1.96 * ep_acumulo, coef_acumulo + 1.96 * ep_acumulo,
   p_acumulo, ifelse(isTRUE(criterio_acumulo), "SIM", "NÃO"))
di("  progresso não positivo: coef = %.3f (EP %.3f) [%.3f; %.3f], p = %.4f → %s",
   coef_progresso, ep_progresso, coef_progresso - 1.96 * ep_progresso,
   coef_progresso + 1.96 * ep_progresso, p_progresso, ifelse(isTRUE(criterio_progresso), "SIM", "NÃO"))
veredito <- ifelse(isTRUE(criterio_acumulo) && isTRUE(criterio_progresso),
                   "H1 SUSTENTADA", "H1 NÃO SUSTENTADA")
di("  %s", veredito)
di("")
di("Ressalva que acompanha o veredito: os rótulos de diretividade são do juiz")
di("`gemini-3.1-pro-preview`. Sem kappa contra codificação humana (>= 0,60) nesta execução, isto")
di("é classificação automática, não resultado.")

writeLines(linhas, file.path(saida, "h1_ordinal.txt"))
cat(paste(linhas, collapse = "\n"), "\n")

esc <- function(x) if (is.null(x) || length(x) == 0 || !is.finite(x)) "null" else format(x)
origens_json <- paste(sapply(names(por_origem), function(o) sprintf(
  '{"origem": "%s", "coef": %s, "ep": %s, "p": %s}', o,
  esc(por_origem[[o]][1]), esc(por_origem[[o]][2]), esc(por_origem[[o]][4]))), collapse = ", ")

# ---- O valor perigoso, e a ressalva que não o larga -------------------------------------------
# Emitido em .json, .csv e .tex além do .txt. Se algum destes caminhos deixar de escrever a
# ressalva, `conferir_ciclos.py` reprova — é por isso que a ressalva é montada uma vez, aqui, e
# reutilizada em todos, em vez de ser reescrita em cada formato.
s2 <- linha_de(s2a, "estagnacao_acumulada")
sens_json <- if (is.null(s2)) "null" else sprintf(
  '{"coef": %s, "ep": %s, "p": %s, "n": %d, "ressalva": "%s"}',
  esc(s2[1]), esc(s2[2]), esc(s2[4]), nrow(droplevels(subset(bloqueados, prioridade != 3))),
  json_str(RESSALVA))

writeLines(
  c("sensibilidade,efeito,coef,ep,ic_inf,ic_sup,p,n,ressalva",
    if (is.null(s2)) character() else sprintf(
      "prioridade_acumulo,estagnacao_acumulada,%.4f,%.4f,%.4f,%.4f,%.4f,%d,%s",
      s2[1], s2[2], s2[1] - 1.96 * s2[2], s2[1] + 1.96 * s2[2], s2[4],
      nrow(droplevels(subset(bloqueados, prioridade != 3))), csv_campo(RESSALVA))),
  file.path(saida, "sensibilidade_prioridade.csv"))

dir.create(file.path(saida, "tabelas"), showWarnings = FALSE, recursive = TRUE)
writeLines(sprintf(
'%% Gerado por `analise_tese/h1_ordinal_exec.R` — sensibilidade de prioridade (execução %s)
%% ATENÇÃO: este valor não pode ser publicado sem a ressalva em \\fonte{}. Ver conferir_ciclos.py.
\\begin{table}[htbp]
  \\centering
  \\caption{Sensibilidade declarada: efeito do acúmulo excluindo os itens de prioridade 3.}
  \\label{tab:res-h1-sens-prioridade}
  \\small
  \\begin{tabular}{P{0.30\\textwidth}P{0.14\\textwidth}P{0.14\\textwidth}P{0.22\\textwidth}P{0.10\\textwidth}}
    \\hline
    \\textbf{Ajuste} & \\textbf{Coef.} & \\textbf{EP} & \\textbf{IC 95\\%%} & \\textbf{p} \\\\
    \\hline
    Acúmulo, sem prioridade 3 (n = %d) & %.3f & %.3f & [%.3f; %.3f] & %.4f \\\\
    \\hline
    Acúmulo, ajuste 1b (todos, n = %d) & %.3f & %.3f & [%.3f; %.3f] & %.4f \\\\
    \\hline
  \\end{tabular}
  \\fonte{Elaborado pelo autor. %s}
\\end{table}',
  exec, nrow(droplevels(subset(bloqueados, prioridade != 3))),
  s2[1], s2[2], s2[1] - 1.96 * s2[2], s2[1] + 1.96 * s2[2], s2[4],
  nrow(bloqueados), coef_acumulo, ep_acumulo,
  coef_acumulo - 1.96 * ep_acumulo, coef_acumulo + 1.96 * ep_acumulo, p_acumulo,
  tex_str(RESSALVA)),
  file.path(saida, "tabelas", "tab_sensibilidade_prioridade.tex"))
json <- sprintf('{
  "execucao": "%s",
  "pacote": "ordinal %s (R %s), clmm, ligação logit, aproximação de Laplace",
  "n_elegiveis": %d,
  "n_bloqueados": %d,
  "prefixos_bloqueados": %d,
  "estrutura_aleatoria_reportada": "(1|item) + (1|prefixo)",
  "estrutura_aleatoria_simplificada": true,
  "motivo_simplificacao": "um diálogo de referência por item em bancada: item e diálogo são o mesmo fator",
  "acumulo": {"coef": %s, "ep": %s, "p": %s, "positivo_a_5pc": %s},
  "progresso": {"coef": %s, "ep": %s, "p": %s, "nao_positivo": %s},
  "acumulo_por_origem": [%s],
  "sensibilidade_prioridade_3": %s,
  "veredito": "%s",
  "kappa_desta_execucao": null,
  "ressalva": "classificação automática; sem kappa >= 0,60 nesta execução não é resultado"
}', exec, as.character(packageVersion("ordinal")), paste0(R.version$major, ".", R.version$minor),
    nrow(dados), nrow(bloqueados), length(unique(as.character(bloqueados$prefixo_id))),
    esc(coef_acumulo), esc(ep_acumulo), esc(p_acumulo), tolower(as.character(criterio_acumulo)),
    esc(coef_progresso), esc(ep_progresso), esc(p_progresso), tolower(as.character(criterio_progresso)),
    origens_json, sens_json, veredito)
writeLines(json, file.path(saida, "h1_ordinal.json"))
