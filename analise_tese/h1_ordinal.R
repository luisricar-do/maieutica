# Tarefa 1 — modelo ordinal misto de H1 (Subseção 4.3.5 da metodologia).
#
# Resposta: diretividade do turno gerado, ordinal de quatro níveis.
# Especificação declarada:
#   diretividade ~ movimento_{k-1} * estagnacao_acumulada + k
#                  + (1|item) + (1|diálogo) + (1|prefixo)
#
# Duas coisas que o desenho impõe e que o ajuste tem de declarar, não contornar:
#   1. Em bancada há um diálogo de referência por item — «diálogo» e «item» são o mesmo fator.
#   2. `estagnacao_acumulada` é contada desde o último progresso, logo vale 0 se e só se o
#      movimento é PROGRESSO. Movimento e acumulado são, por construção, parcialmente
#      redundantes, e a interação não é estimável no nível PROGRESSO.
# Daí os três ajustes: o especificado (que mostra o que fica aliasado), o do acúmulo sobre os
# turnos bloqueados, e o do progresso sobre todos.
#
#   Rscript analise_tese/h1_ordinal.R   # → saida/h1_ordinal.txt e saida/h1_ordinal.json

suppressPackageStartupMessages(library(ordinal))

raiz <- dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1]))
if (is.na(raiz) || raiz == "") raiz <- "analise_tese"
saida <- file.path(raiz, "saida")
dados <- read.csv(file.path(saida, "h1_modelo.csv"), stringsAsFactors = FALSE)

dados$diretividade <- factor(dados$diretividade, levels = 0:3, ordered = TRUE)
dados$movimento <- relevel(factor(dados$movimento), ref = "ESTAGNACAO")
dados$item_id <- factor(dados$item_id)
dados$prefixo_id <- factor(dados$prefixo_id)
dados$dialogo_id <- factor(dados$dialogo_id)
dados$comprimento_c <- as.numeric(scale(dados$comprimento, center = TRUE, scale = FALSE)) / 100

linhas <- character()
di <- function(...) linhas <<- c(linhas, sprintf(...))

di("Turnos elegíveis: %d (condição A, prefixos de referência, k >= 2, sem pedido explícito).", nrow(dados))
di("Itens: %d · diálogos: %d · prefixos: %d · execuções por prefixo: %d",
   nlevels(dados$item_id), nlevels(dados$dialogo_id), nlevels(dados$prefixo_id),
   max(table(dados$prefixo_id)))
di("Exclusões a montante: turnos de abertura (k=1, movimento NENHUM), prefixos de pressão")
di("  (movimento PEDIDO_EXPLICITO) e as condições B e C, que não têm política de contingência.")
di("")
di("Confundimento estrutural entre movimento e acumulado:")
tab <- table(dados$movimento, dados$estagnacao_acumulada)
linhas <<- c(linhas, capture.output(print(tab)), "")
di("PROGRESSO só ocorre com acumulado 0; ESTAGNACAO e REGRESSAO só com acumulado >= 1.")
di("")

ajustar <- function(formula, dados, rotulo) {
  di("========================================================================")
  di("%s", rotulo)
  di("  n = %d · fórmula: %s", nrow(dados), paste(deparse(formula), collapse = ""))
  ajuste <- tryCatch(
    clmm(formula, data = dados, Hess = TRUE, link = "logit"),
    error = function(e) { di("  NÃO CONVERGE: %s", conditionMessage(e)); NULL },
    warning = function(w) {
      di("  AVISO: %s", conditionMessage(w))
      suppressWarnings(clmm(formula, data = dados, Hess = TRUE, link = "logit"))
    })
  if (is.null(ajuste)) { di(""); return(NULL) }
  co <- coef(summary(ajuste))
  fixos <- co[!grepl("\\|", rownames(co)), , drop = FALSE]
  ic <- cbind(fixos[, 1] - 1.96 * fixos[, 2], fixos[, 1] + 1.96 * fixos[, 2])
  di("  %-34s %9s %8s %9s %9s %9s", "efeito", "coef", "EP", "IC inf", "IC sup", "p")
  for (i in seq_len(nrow(fixos))) {
    di("  %-34s %9.3f %8.3f %9.3f %9.3f %9.4f",
       rownames(fixos)[i], fixos[i, 1], fixos[i, 2], ic[i, 1], ic[i, 2], fixos[i, 4])
  }
  va <- tryCatch(VarCorr(ajuste), error = function(e) NULL)
  if (!is.null(va)) {
    for (g in names(va)) {
      v <- as.numeric(va[[g]])[1]
      di("  variância aleatória %-22s %9.4f %s", g, v,
         ifelse(v < 1e-6, "(singular — o fator não separa nada)", ""))
    }
  }
  di("  logLik = %.2f · AIC = %.2f · convergência: %s",
     as.numeric(logLik(ajuste)), AIC(ajuste),
     ifelse(ajuste$optRes$convergence == 0, "sim", paste("código", ajuste$optRes$convergence)))
  di("")
  ajuste
}

# -- Ajuste 0: a especificação declarada, tal como está escrita -------------------------------
m0 <- ajustar(diretividade ~ movimento * estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
              dados, "AJUSTE 0 — especificação declarada (item = diálogo em bancada)")
if (!is.null(m0)) {
  aliasado <- rownames(coef(summary(m0)))[is.na(coef(summary(m0))[, 2])]
  di("Termos não estimáveis no ajuste 0: %s",
     ifelse(length(aliasado) == 0, "nenhum sinalizado pelo R", paste(aliasado, collapse = ", ")))
  di("")
}

# -- Ajuste 0b: o diálogo a par do item, para mostrar que não é identificável ------------------
m0b <- ajustar(diretividade ~ movimento * estagnacao_acumulada + k
                 + (1 | item_id) + (1 | dialogo_id) + (1 | prefixo_id),
               dados, "AJUSTE 0b — com «diálogo» e «item» a par, como a especificação os lista")
di("Em bancada há um diálogo de referência por item: os dois fatores têm os mesmos 25 níveis e a")
di("variância reparte-se arbitrariamente entre eles. A estrutura aleatória reportada é, por isso,")
di("(1|item) + (1|prefixo) — simplificação imposta pelo desenho, não escolha de ajuste.")
di("")

# -- Ajuste 1: o efeito do acúmulo, onde ele é estimável ---------------------------------------
bloqueados <- droplevels(subset(dados, movimento %in% c("ESTAGNACAO", "REGRESSAO")))
m1 <- ajustar(diretividade ~ movimento * estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
              bloqueados, "AJUSTE 1 — efeito do acúmulo, só turnos bloqueados")
m1b <- ajustar(diretividade ~ movimento + estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
               bloqueados, "AJUSTE 1b — idem, sem interação")

# -- Ajuste 2: o efeito do progresso ------------------------------------------------------------
m2 <- ajustar(diretividade ~ movimento + k + (1 | item_id) + (1 | prefixo_id),
              dados, "AJUSTE 2 — efeito do movimento sobre todos os elegíveis (ref.: ESTAGNACAO)")

# -- Sensibilidades ------------------------------------------------------------------------------
ajustar(diretividade ~ movimento + estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
        droplevels(subset(bloqueados, prioridade != 3)),
        "SENSIBILIDADE — acúmulo, excluindo itens de prioridade 3")
ajustar(diretividade ~ movimento + k + (1 | item_id) + (1 | prefixo_id),
        droplevels(subset(dados, prioridade != 3)),
        "SENSIBILIDADE — movimento, excluindo itens de prioridade 3")
for (o in sort(unique(dados$origem))) {
  ajustar(diretividade ~ movimento + estagnacao_acumulada + k + (1 | item_id) + (1 | prefixo_id),
          droplevels(subset(bloqueados, origem == o)),
          sprintf("SENSIBILIDADE — acúmulo, só origem %s", o))
}
ajustar(diretividade ~ movimento + estagnacao_acumulada + k + comprimento_c + (1 | item_id) + (1 | prefixo_id),
        bloqueados, "SENSIBILIDADE — acúmulo com o comprimento do turno como covariável")
ajustar(diretividade ~ movimento + k + comprimento_c + (1 | item_id) + (1 | prefixo_id),
        dados, "SENSIBILIDADE — movimento com o comprimento do turno como covariável")
com_edicao <- droplevels(subset(dados, houve_edicao == "True"))
ajustar(diretividade ~ movimento + k + (1 | item_id),
        com_edicao,
        sprintf("SENSIBILIDADE — subamostra com edição de código (n=%d), variável independente vinda dos casos de teste",
                nrow(com_edicao)))

# -- Veredito -------------------------------------------------------------------------------------
di("========================================================================")
di("VEREDITO DE H1")
criterio_acumulo <- NA; p_acumulo <- NA; coef_acumulo <- NA
if (!is.null(m1b)) {
  co <- coef(summary(m1b))
  if ("estagnacao_acumulada" %in% rownames(co)) {
    coef_acumulo <- co["estagnacao_acumulada", 1]; p_acumulo <- co["estagnacao_acumulada", 4]
    criterio_acumulo <- (coef_acumulo > 0) && (p_acumulo < 0.05)
  }
}
criterio_progresso <- NA; p_progresso <- NA; coef_progresso <- NA
if (!is.null(m2)) {
  co <- coef(summary(m2))
  if ("movimentoPROGRESSO" %in% rownames(co)) {
    coef_progresso <- co["movimentoPROGRESSO", 1]; p_progresso <- co["movimentoPROGRESSO", 4]
    criterio_progresso <- !((coef_progresso > 0) && (p_progresso < 0.05))
  }
}
di("  acúmulo positivo a 5%%: coef = %.3f, p = %.4f → %s",
   coef_acumulo, p_acumulo, ifelse(isTRUE(criterio_acumulo), "SIM", "NÃO"))
di("  progresso não positivo: coef = %.3f, p = %.4f → %s",
   coef_progresso, p_progresso, ifelse(isTRUE(criterio_progresso), "SIM", "NÃO"))
veredito <- ifelse(isTRUE(criterio_acumulo) && isTRUE(criterio_progresso),
                   "H1 SUSTENTADA", "H1 NÃO SUSTENTADA")
di("  %s", veredito)

writeLines(linhas, file.path(saida, "h1_ordinal.txt"))
cat(paste(linhas, collapse = "\n"), "\n")

json <- sprintf('{
  "pacote": "ordinal %s (R %s), clmm, ligação logit, aproximação de Laplace",
  "n_elegiveis": %d,
  "acumulo": {"coef": %s, "p": %s, "positivo_a_5pc": %s},
  "progresso": {"coef": %s, "p": %s, "nao_positivo": %s},
  "veredito": "%s"
}', as.character(packageVersion("ordinal")), paste0(R.version$major, ".", R.version$minor),
    nrow(dados), format(coef_acumulo), format(p_acumulo), tolower(as.character(criterio_acumulo)),
    format(coef_progresso), format(p_progresso), tolower(as.character(criterio_progresso)), veredito)
writeLines(json, file.path(saida, "h1_ordinal.json"))
