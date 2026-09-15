# A ressalva que acompanha a sensibilidade «excluir prioridade 3», onde quer que ela seja gerada.
#
# Esse ajuste é o único do conjunto que dá p < 0,05, e por isso é o número mais perigoso do
# relatório: numa tabela sozinho, lê-se como apoio a H1. Não é. O p aparece porque a exclusão
# remove justamente o item cuja diretividade não escala com o acumulado — a contraprova — e deixa
# a faixa em que H1 se decide povoada pelo caso favorável. Um número com esse mecanismo não pode
# viajar sem o mecanismo.
#
# A ressalva é **construída a partir dos dados**, não escrita à mão: se o banco ou a anotação
# mudarem, ela passa a descrever o que passou a ser verdade, em vez de repetir o que era. Os dois
# scripts que produzem a sensibilidade (`h1_ordinal.R`, do ciclo 1, e `h1_ordinal_exec.R`)
# carregam-na daqui, e `analise_tese/conferir_ciclos.py` reprova se o coeficiente aparecer num
# artefato gerado sem ela.
#
# Sem acentos nem aspas: o texto atravessa JSON, CSV e `\fonte{}` de LaTeX.

prefixos_da_faixa <- function(dd, minimo = 4) {
  faixa <- subset(dd, estagnacao_acumulada >= minimo)
  tapply(as.character(faixa$prefixo_id), as.character(faixa$item_id),
         function(p) length(unique(p)))
}

#' @param bloqueados turnos bloqueados elegiveis, com `prioridade`, `item_id`, `prefixo_id`,
#'   `estagnacao_acumulada` e `diretividade`.
#' @param p p do coeficiente do acumulo no ajuste sem prioridade 3, medido nesta corrida. A
#'   abertura da ressalva depende dele: em `cap5` da 0,0357 e e o unico coeficiente de acumulo
#'   abaixo de 0,05 em todo o conjunto; no ciclo 1 da 0,1986 e nem sequer e significativo. Uma
#'   ressalva que afirmasse significancia nos dois casos seria falsa num deles.
ressalva_prioridade <- function(bloqueados, p = NA_real_) {
  antes <- prefixos_da_faixa(bloqueados)
  depois <- prefixos_da_faixa(subset(bloqueados, prioridade != 3))
  caidos <- setdiff(names(antes), names(depois))
  total_antes <- sum(antes)
  total_depois <- sum(depois)
  if (length(caidos) == 0) {
    return(paste0(
      "ATENCAO: a exclusao de prioridade 3 nao remove nenhum item da faixa de acumulado >= 4 ",
      "nesta corrida, portanto o mecanismo descrito no ciclo 2 nao se aplica aqui. A sensibilidade ",
      "continua a nao decidir H1 — quem decide e o ajuste 1b sobre a populacao inteira —, mas a ",
      "explicacao do p tem de ser reconferida contra estes dados antes de ser citada."))
  }
  # O item caido que mais prefixos tinha na faixa: e dele que vem a contraprova.
  dono <- caidos[which.max(antes[caidos])]
  serie <- subset(bloqueados, as.character(item_id) == dono)
  medias <- tapply(as.numeric(as.character(serie$diretividade)), serie$estagnacao_acumulada, mean)
  escala <- paste(sprintf("acc %s = %.3f", names(medias), medias), collapse = "; ")
  rho <- suppressWarnings(cor(as.numeric(names(medias)), as.numeric(medias), method = "spearman"))
  restantes <- if (length(depois) == 0) "nenhum" else
    paste(sprintf("%s (%d)", names(depois), depois), collapse = ", ")
  abertura <- if (!is.finite(p)) {
    "NAO SUSTENTA H1. "
  } else if (p < 0.05) {
    paste0("NAO SUSTENTA H1, apesar de p = ", sprintf("%.4f", p), ". O mecanismo que produz esse ",
           "p e uma exclusao que remove a contraprova. ")
  } else {
    paste0("NAO SUSTENTA H1: p = ", sprintf("%.4f", p), ", nem sequer significativo. A ressalva ",
           "acompanha o valor a mesma, porque o que a exclusao faz a populacao e o mesmo em ",
           "qualquer corrida, e e por isso que este ajuste nao serve para decidir H1 em nenhuma. ")
  }
  paste0(
    abertura, "Excluir prioridade 3 retira ", dono, ", dono de ",
    antes[dono], " dos ", total_antes, " prefixos da faixa de acumulado >= 4 — a faixa em que a ",
    "politica escala e onde H1 se decide. A diretividade media desse item NAO escala com o ",
    "acumulado (", escala, "; Spearman rho = ", sprintf("%.3f", rho), "), portanto e ele o caso ",
    "desfavoravel. Removido, a faixa fica com ", total_depois, " prefixos em ", length(depois),
    " itens: ", restantes, ". O ajuste principal que decide H1 e o 1b, sobre a populacao inteira, ",
    "e da coeficiente do acumulo nao distinguivel de zero. Citar este numero sem este paragrafo ",
    "e indefensavel assim que alguem abrir os dados.")
}

#' Escapes para os tres formatos de saida. Sem eles a unica frase que impede o numero de ser mal
#' citado sai ilegivel — `<` e `>` em modo texto do LaTeX saem como ¡ e ¿, e a ressalva usa ambos.
json_str <- function(s) gsub("\n", " ", gsub('"', '\\\\"', s))

csv_campo <- function(s) paste0('"', gsub('"', '""', gsub("\n", " ", s)), '"')

tex_str <- function(s) {
  s <- gsub("`", "", s)
  s <- gsub("([&%$#{}])", "\\\\\\1", s)
  s <- gsub("_", "\\\\_", s)
  s <- gsub(">=", "$\\\\geq$", s)
  s <- gsub("<=", "$\\\\leq$", s)
  s <- gsub("<", "$<$", s)
  gsub(">", "$>$", s)
}
