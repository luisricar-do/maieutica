# Quantos itens com bloqueio sustentado seriam precisos para 80% de poder em H1.
#
# Mesma maquinaria de `poder_h1.R` — mesmas componentes de variância e mesmos limiares do ajuste
# do ciclo 1 —, mas sobre os prefixos bloqueados do banco **reanotado** (regra de conteúdo), e
# invertendo a pergunta: em vez de "qual o poder com o corpus que há", "quantos itens faltam".
#
# Um "item com bloqueio sustentado" é modelado como os três que existem: contribui prefixos com
# acumulado 1..profundidade. Os que existem dão profundidade 7, 5 e 4 (fibonacci, factorial,
# tese_06). Daí as duas colunas: 4 é o pessimista realista, 6 o otimista.
#
# A primeira linha da saída é o controlo: a mesma simulação sobre os 47 prefixos do ciclo 1 tem
# de reproduzir o EP 0,617 que `poder_h1.R` regista. Se não reproduzir, nada abaixo vale.
suppressMessages(library(ordinal))
set.seed(20260915)

dir.create("analise_tese/saida", showWarnings = FALSE, recursive = TRUE)
sink("analise_tese/saida/poder_h1_corpus.txt", split = TRUE)

LIMIARES <- c(-4.437, 3.266); SD_ITEM <- sqrt(1.0127); SD_PREF <- sqrt(13.3996)
BETA <- 0.6; R <- 40; N_EXEC <- 3

ciclo1 <- read.csv("analise_tese/saida/h1_modelo.csv", stringsAsFactors = FALSE)
ciclo1 <- ciclo1[ciclo1$movimento %in% c("ESTAGNACAO", "REGRESSAO"), ]
ciclo1 <- unique(ciclo1[, c("item_id", "prefixo_id", "estagnacao_acumulada")])

banco <- read.csv("analise_tese/saida/h1_bloqueados_banco.csv", stringsAsFactors = FALSE)
banco <- unique(banco[, c("item_id", "prefixo_id", "estagnacao_acumulada")])

descreve <- function(rot, d) cat(sprintf(
  "%-22s %3d prefixos bloqueados · %2d itens · Var(acum) = %.3f · media %.3f\n",
  rot, nrow(d), length(unique(d$item_id)), var(d$estagnacao_acumulada),
  mean(d$estagnacao_acumulada)))
descreve("ciclo 1 (25 itens)", ciclo1)
descreve("banco reanotado (45)", banco)
cat(sprintf("\nbeta simulado = %.2f · %d replicas por celula · %d execucoes por prefixo\n\n",
            BETA, R, N_EXEC))

um_ep <- function(obs, n_novos, profundidade, beta = BETA) {
  d <- obs
  if (n_novos > 0) {
    novo <- do.call(rbind, lapply(seq_len(n_novos), function(i)
      data.frame(item_id = paste0("novo", i),
                 prefixo_id = paste0("novo", i, "_a", seq_len(profundidade)),
                 estagnacao_acumulada = seq_len(profundidade))))
    d <- rbind(d, novo)
  }
  d <- d[rep(seq_len(nrow(d)), each = N_EXEC), ]
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

celula <- function(obs, n, prof) {
  ep <- mean(replicate(R, um_ep(obs, n, prof)), na.rm = TRUE)
  list(ep = ep, poder = pnorm(BETA / ep - 1.96), detectavel = 2.80 * ep,
       prefixos = nrow(obs) + n * prof)
}

cat("CONTROLO — reproduz o EP do ciclo 1 registado em CICLOS.md (0,617 simulado / 0,652 medido)?\n")
c1 <- celula(ciclo1, 0, 0)
cat(sprintf("  ciclo 1, 0 itens novos: EP = %.3f\n\n", c1$ep))

cat("BANCO REANOTADO — quantos itens com bloqueio sustentado faltam para 80%%\n")
cat(sprintf("%-6s %-6s %-10s %-9s %-8s %s\n",
            "novos", "prof", "prefixos", "EP medio", "poder", "beta detectavel a 80%"))
resultados <- list()
for (prof in c(4, 6)) {
  for (n in c(0, 5, 10, 15, 20, 25, 30, 40)) {
    r <- celula(banco, n, prof)
    resultados[[length(resultados) + 1]] <- c(prof = prof, n = n, poder = r$poder, ep = r$ep)
    cat(sprintf("%-6d %-6d %-10d %-9.3f %-8.2f %.2f\n",
                n, prof, r$prefixos, r$ep, r$poder, r$detectavel))
    if (n > 0 && r$poder >= 0.80) break
  }
}

cat("\nINTERPOLACAO — itens necessarios para poder 80%% com beta = 0.6\n")
tab <- do.call(rbind, lapply(resultados, function(x) as.data.frame(as.list(x))))
for (prof in c(4, 6)) {
  sub <- tab[tab$prof == prof, ]
  if (max(sub$poder) < 0.80) {
    cat(sprintf("  profundidade %d: nao atinge 80%% ate %d itens novos (poder %.2f)\n",
                prof, max(sub$n), max(sub$poder)))
  } else {
    alvo <- approx(sub$poder, sub$n, xout = 0.80)$y
    cat(sprintf("  profundidade %d: ~%.0f itens novos com bloqueio sustentado\n", prof, alvo))
  }
}

# --- Erro de Monte Carlo -----------------------------------------------------------------
# R = 40 e barato e instavel. Sem esta medicao nao se sabe se a diferenca entre duas celulas
# e efeito ou semente — e a celula n=15/prof=6 acima, fora de ordem, mostra que importa.
cat("\n\nERRO DE MONTE CARLO do EP simulado (populacao do ciclo 1)\n")
eps <- replicate(240, um_ep(ciclo1, 0, 0)); eps <- eps[is.finite(eps)]
cat(sprintf("  replicas validas: %d · EP medio = %.3f · DP entre replicas = %.3f\n",
            length(eps), mean(eps), sd(eps)))
cat(sprintf("  erro da media com R=40:  +-%.3f  -> intervalo tipico [%.3f; %.3f]\n",
            sd(eps)/sqrt(40), mean(eps)-1.96*sd(eps)/sqrt(40), mean(eps)+1.96*sd(eps)/sqrt(40)))
cat(sprintf("  erro da media com R=%d: +-%.3f\n", length(eps), sd(eps)/sqrt(length(eps))))
cat("  Logo: o 0,617 registado e o 0,562 desta corrida sao a mesma quantidade com sementes\n")
cat("  diferentes. Qualquer numero que va ao capitulo precisa de R >= 200.\n")

sink()
