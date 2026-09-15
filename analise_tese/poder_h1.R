# Precisão do efeito do acúmulo em H1, por simulação sobre a estrutura ajustada.
# O acumulado é covariável de nível-prefixo: contam os prefixos bloqueados e a
# dispersão do acumulado entre eles. Estima-se o EP e deriva-se o poder por
# poder = Phi(beta/EP - 1.96), em vez de contar rejeições.
suppressMessages(library(ordinal))
set.seed(20260914)

sink("analise_tese/saida/poder_h1.txt", split = TRUE)
dados <- read.csv("analise_tese/saida/h1_modelo.csv", stringsAsFactors = FALSE)
bloq <- dados[dados$movimento %in% c("ESTAGNACAO", "REGRESSAO"), ]
obs <- unique(bloq[, c("item_id", "prefixo_id", "estagnacao_acumulada")])

LIMIARES <- c(-4.437, 3.266); SD_ITEM <- sqrt(1.0127); SD_PREF <- sqrt(13.3996)
cat(sprintf("observado: %d prefixos bloqueados · %d itens · Var(acum) = %.2f\n\n",
            nrow(obs), length(unique(obs$item_id)), var(obs$estagnacao_acumulada)))

um_ep <- function(n_novos, profundidade, beta, n_exec = 3) {
  d <- obs[, c("item_id", "prefixo_id", "estagnacao_acumulada")]
  if (n_novos > 0) {
    novo <- do.call(rbind, lapply(seq_len(n_novos), function(i)
      data.frame(item_id = paste0("novo", i),
                 prefixo_id = paste0("novo", i, "_a", seq_len(profundidade)),
                 estagnacao_acumulada = seq_len(profundidade))))
    d <- rbind(d, novo)
  }
  d <- d[rep(seq_len(nrow(d)), each = n_exec), ]
  ui <- setNames(rnorm(length(unique(d$item_id)), 0, SD_ITEM), unique(d$item_id))
  up <- setNames(rnorm(length(unique(d$prefixo_id)), 0, SD_PREF), unique(d$prefixo_id))
  eta <- beta * d$estagnacao_acumulada + ui[d$item_id] + up[d$prefixo_id]
  cum <- sapply(LIMIARES, function(a) plogis(a - eta))
  pr <- cbind(cum[, 1], cum[, 2] - cum[, 1], 1 - cum[, 2])
  d$y <- factor(apply(pr, 1, function(r) sample(1:3, 1, prob = pmax(r, 1e-9))),
                levels = 1:3, ordered = TRUE)
  if (length(unique(d$y)) < 2) return(NA)
  co <- tryCatch(
    coef(summary(clmm(y ~ estagnacao_acumulada + (1|item_id) + (1|prefixo_id),
                      data = d, link = "logit", Hess = TRUE))),
    error = function(e) NULL, warning = function(w) NULL)
  if (is.null(co) || !"estagnacao_acumulada" %in% rownames(co)) return(NA)
  ep <- co["estagnacao_acumulada", "Std. Error"]
  if (!is.finite(ep)) NA else ep
}

R <- 40
cat(sprintf("réplicas por célula: %d\n\n", R))
cat(sprintf("%-12s %-6s %-11s %-8s %s\n", "itens novos", "prof", "prefixos", "EP médio",
            "beta detectável a 80% | poder se beta=0.6"))
for (cfg in list(c(0,6), c(10,6), c(20,6), c(35,6), c(20,4))) {
  n <- cfg[1]; prof <- cfg[2]
  eps <- replicate(R, um_ep(n, prof, 0.6))
  ep <- mean(eps, na.rm = TRUE)
  cat(sprintf("%-12d %-6d %-11d %-8.3f %.2f | %.2f\n", n, prof,
              nrow(obs) + n * prof, ep, 2.80 * ep, pnorm(0.6 / ep - 1.96)))
}

sink()
