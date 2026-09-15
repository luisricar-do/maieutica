# Reanotação dos 20 itens novos — regra de conteúdo do ciclo 1

Aplicada em 2026-09-15, **antes** da corrida somativa, na sequência do achado registado em
`CICLOS.md`: os 20 itens novos estavam anotados pelo estado do código (nenhum dos 120 turnos sem
edição era progresso) e os 25 do ciclo 1 pelo conteúdo da fala (78 de 114 eram).

A regra aplicada é a que se extrai dos 25 itens do ciclo 1, não uma regra nova:

- **PROGRESSO** — conteúdo novo e **correto**: observação certa sobre a saída, resposta certa à
  pergunta do tutor (mesmo curta), intuição parcial certa, pergunta que avança.
- **ESTAGNACAO** — bloqueio declarado: "não sei", "não entendi", "continua igual", resposta fora
  do foco, ou pedir que o tutor forneça.
- **REGRESSAO** — afirmação **errada**: hipótese errada, traço errado, expectativa errada, dar
  por correto ou por resolvido o que não está.

98 dos 100 turnos mudaram: 93 `ESTAGNACAO`→`PROGRESSO` e 5 `ESTAGNACAO`→`REGRESSAO`. Os turnos
já anotados `REGRESSAO` (o sexto de cada item) e `PROGRESSO` (o da correção) ficaram como
estavam, e não constam da tabela.

A coluna **nota** justifica todo turno que não virou `PROGRESSO` e as duas chamadas que
considero discutíveis — são as que convém rever primeiro. `referencia_autoria` continua
`autor_com_assistencia`.

Reproduzível por `scripts/reanotar_movimento.py`.

| item | turno | de | para | fala do estudante | nota |
|---|---|---|---|---|---|
| tese_07_soma_multiplos | E[2] | ESTAGNACAO | **PROGRESSO** | E o ultimo, o seis. Mas nao sei o que isso quer dizer. |  |
| tese_07_soma_multiplos | E[4] | ESTAGNACAO | **PROGRESSO** | Na linha do se, acho. Eu ja conferi essa condicao um monte de vezes e ela esta certa. | PRO discutível: responde onde os três entram e afirma, corretamente, que a condição está certa — o tutor confirma. |
| tese_07_soma_multiplos | E[8] | ESTAGNACAO | **PROGRESSO** | Le soma igual a zero, depois o se, depois soma mais valores de i. Continuo sem ver o problema. |  |
| tese_07_soma_multiplos | E[10] | ESTAGNACAO | **REGRESSAO** | Uma a cada volta, acho. Mas ela so poe zero, nao tira nada de lugar nenhum. | REG: acerta 'uma a cada volta', mas afirma que a linha 'só põe zero, não tira nada' — hipótese incorreta afirmada. |
| tese_07_soma_multiplos | E[12] | ESTAGNACAO | **PROGRESSO** | Zero. Mas eu preciso zerar em algum lugar, senao a soma comeca com lixo. |  |
| tese_08_troca_valores | E[2] | ESTAGNACAO | **PROGRESSO** | Nao aparece em lugar nenhum. Sumiu. |  |
| tese_08_troca_valores | E[4] | ESTAGNACAO | **PROGRESSO** | Sao as duas atribuicoes, a igual b e b igual a. Elas estao uma de cada lado, eu fiz de proposito para a troca ficar simetrica. |  |
| tese_08_troca_valores | E[8] | ESTAGNACAO | **PROGRESSO** | Vale 7. Mas isso e o que eu quero, a tem que ficar com o valor de b. |  |
| tese_08_troca_valores | E[10] | ESTAGNACAO | **PROGRESSO** | Recebe a, que e 7. Entao b tambem fica 7. Mas eu escrevi b igual a para ele receber o 3. |  |
| tese_08_troca_valores | E[12] | ESTAGNACAO | **PROGRESSO** | A linha de cima. Mas eu preciso das duas atribuicoes, senao nao troca. |  |
| tese_09_posicao_maior | E[2] | ESTAGNACAO | **PROGRESSO** | Por um. Mas nao sei de onde vem esse um. |  |
| tese_09_posicao_maior | E[4] | ESTAGNACAO | **PROGRESSO** | Um antes do laco e um dentro do se. Neste caso foi o de dentro, porque o 9 e maior que o 3. |  |
| tese_09_posicao_maior | E[8] | ESTAGNACAO | **REGRESSAO** | Vale 1. E o programa imprimiu 1. Entao esta certo. | REG: 'Vale 1. E o programa imprimiu 1. Então está certo' — dá por correto o que está defeituoso (cf. tese_02 no ciclo 1). |
| tese_09_posicao_maior | E[10] | ESTAGNACAO | **PROGRESSO** | i igual a 1 corresponde ao segundo, porque o vetor comeca em zero. Nao entendi o que isso muda. |  |
| tese_09_posicao_maior | E[12] | ESTAGNACAO | **PROGRESSO** | Indice 1 e posicao 2. Mas a linha guarda o indice. |  |
| tese_10_faixa_valores | E[2] | ESTAGNACAO | **PROGRESSO** | Nenhum. Ele contou todos. |  |
| tese_10_faixa_valores | E[4] | ESTAGNACAO | **PROGRESSO** | A primeira da verdadeiro, 25 e maior que 10. A segunda da falso, 25 nao e menor que 20. Eu escrevi as duas comparacoes certas. |  |
| tese_10_faixa_valores | E[8] | ESTAGNACAO | **PROGRESSO** | E o ou. Mas eu quis dizer que o numero tem que estar de um jeito ou de outro dentro da faixa. |  |
| tese_10_faixa_valores | E[10] | ESTAGNACAO | **PROGRESSO** | Devolve verdadeiro. Por isso o 25 entrou. |  |
| tese_10_faixa_valores | E[12] | ESTAGNACAO | **PROGRESSO** | As duas. Mas nao sei como escrever isso. |  |
| tese_11_soma_ate_zero | E[2] | ESTAGNACAO | **PROGRESSO** | Valor diferente de zero. E eu quero mesmo que ele pare quando for zero. |  |
| tese_11_soma_ate_zero | E[4] | ESTAGNACAO | **PROGRESSO** | Eu digitar outro numero. Mas ele nem me pede. |  |
| tese_11_soma_ate_zero | E[8] | ESTAGNACAO | **PROGRESSO** | Esta em cima, antes das chaves abrirem. |  |
| tese_11_soma_ate_zero | E[10] | ESTAGNACAO | **PROGRESSO** | Uma so. Mas ela e que da o primeiro valor, sem ela o enquanto nem comeca. |  |
| tese_11_soma_ate_zero | E[12] | ESTAGNACAO | **PROGRESSO** | A cada volta. Mas so tenho um leia. |  |
| tese_12_menor_valor | E[2] | ESTAGNACAO | **PROGRESSO** | Na linha em que eu digo menor igual a zero, antes do laco. |  |
| tese_12_menor_valor | E[4] | ESTAGNACAO | **PROGRESSO** | O se teria de ser verdadeiro. Mas ele compara valores com menor, e a comparacao esta certa, eu conferi. |  |
| tese_12_menor_valor | E[8] | ESTAGNACAO | **PROGRESSO** | Com zero. E 3 nao e menor que zero, entao nao entra. |  |
| tese_12_menor_valor | E[10] | ESTAGNACAO | **REGRESSAO** | Nenhuma, todos sao positivos. Mas a comparacao nao deveria ser ao contrario, entao? | REG: propõe inverter a comparação, que procuraria o maior (cf. 65_66 no ciclo 1, proposta errada = regressão). |
| tese_12_menor_valor | E[12] | ESTAGNACAO | **PROGRESSO** | Mas eu preciso comecar com alguma coisa, senao nao tenho com que comparar. |  |
| tese_13_acima_da_media | E[2] | ESTAGNACAO | **PROGRESSO** | Qualquer coisa menor que 1, que e o meu menor numero. Zero, por exemplo. |  |
| tese_13_acima_da_media | E[4] | ESTAGNACAO | **PROGRESSO** | Recebe zero antes dos lacos e recebe soma dividido por n depois. As duas estao la, eu nao esqueci de calcular. |  |
| tese_13_acima_da_media | E[8] | ESTAGNACAO | **PROGRESSO** | A contagem. Depois a soma, e por ultimo a divisao. |  |
| tese_13_acima_da_media | E[10] | ESTAGNACAO | **PROGRESSO** | Nenhuma. Mas a linha da divisao esta escrita ali no programa. |  |
| tese_13_acima_da_media | E[12] | ESTAGNACAO | **PROGRESSO** | Zero, que foi o que eu pus no comeco. Mas eu preciso desse zero para inicializar. |  |
| tese_14_soma_incompleta | E[2] | ESTAGNACAO | **PROGRESSO** | O 1 e o 2. Ficou faltando o 3. |  |
| tese_14_soma_incompleta | E[4] | ESTAGNACAO | **PROGRESSO** | Precisaria de tres. Nao sei quantas ele da, a condicao tem um menos um que eu pus para nao passar do fim do vetor. |  |
| tese_14_soma_incompleta | E[8] | ESTAGNACAO | **PROGRESSO** | Ate 2, porque para em i menor que 3. E as posicoes sao 0, 1 e 2. |  |
| tese_14_soma_incompleta | E[10] | ESTAGNACAO | **PROGRESSO** | Ate 1. Visita a 0 e a 1 e para. |  |
| tese_14_soma_incompleta | E[12] | ESTAGNACAO | **PROGRESSO** | Falta a 2. Mas o outro laco, o que le, usa i menor que n e nao estoura. |  |
| tese_15_classifica_nota | E[2] | ESTAGNACAO | **PROGRESSO** | As duas primeiras. Oito e maior que cinco e maior que sete. |  |
| tese_15_classifica_nota | E[4] | ESTAGNACAO | **PROGRESSO** | Um so. Mas cada uma das minhas condicoes esta certa, eu conferi uma por uma. |  |
| tese_15_classifica_nota | E[8] | ESTAGNACAO | **PROGRESSO** | A de cinco, porque esta escrita em cima. |  |
| tese_15_classifica_nota | E[10] | ESTAGNACAO | **PROGRESSO** | Nao, porque ja entrou na de cinco. Mas eu preciso das duas condicoes. |  |
| tese_15_classifica_nota | E[12] | ESTAGNACAO | **PROGRESSO** | Que ele nunca roda. Mas se eu tirar a de cinco, quem tem seis fica sem resposta. |  |
| tese_16_conta_fora_do_se | E[2] | ESTAGNACAO | **PROGRESSO** | Nenhum. Contou todos, inclusive os negativos. |  |
| tese_16_conta_fora_do_se | E[4] | ESTAGNACAO | **PROGRESSO** | E a linha do quantos. Esta dentro do laco, e o se esta logo acima dela. |  |
| tese_16_conta_fora_do_se | E[8] | ESTAGNACAO | **PROGRESSO** | Nada. Ficaram vazias. |  |
| tese_16_conta_fora_do_se | E[10] | ESTAGNACAO | **REGRESSAO** | Nao decide nada. Mas o quantos esta logo abaixo, entao ele conta quando a condicao e verdadeira. | REG: afirma que 'ele conta quando a condição é verdadeira', que é falso para o código como está. |
| tese_16_conta_fora_do_se | E[12] | ESTAGNACAO | **PROGRESSO** | Depois. Entao ela pertence ao laco e nao ao se. |  |
| tese_17_media_dos_pares | E[2] | ESTAGNACAO | **PROGRESSO** | Nao sei. A soma dos pares da 6, e 6 dividido por 2 da 3, que e o certo. | PRO discutível: abre com 'Não sei' mas estabelece 6/2=3, conteúdo novo e correto. |
| tese_17_media_dos_pares | E[4] | ESTAGNACAO | **PROGRESSO** | Por n. E n vale 4, porque eu digitei quatro numeros. |  |
| tese_17_media_dos_pares | E[8] | ESTAGNACAO | **PROGRESSO** | Conta quantos pares tem. E o n conta todos os numeros. |  |
| tese_17_media_dos_pares | E[10] | ESTAGNACAO | **PROGRESSO** | Tem o quantos, que eu incremento junto com a soma. Mas ele nao aparece na conta. |  |
| tese_17_media_dos_pares | E[12] | ESTAGNACAO | **PROGRESSO** | Em lugar nenhum. Ele so cresce e nunca e usado. |  |
| tese_18_busca_mensagem | E[2] | ESTAGNACAO | **REGRESSAO** | O laco. Mas a mensagem nao tem nada a ver com o laco, ela e a resposta final. | REG: 'a mensagem não tem nada a ver com o laço' é falso sobre o código escrito (cf. 56_15 no ciclo 1). |
| tese_18_busca_mensagem | E[4] | ESTAGNACAO | **PROGRESSO** | As chaves. Mas eu abri o se depois do outro se, nao dentro dele. |  |
| tese_18_busca_mensagem | E[8] | ESTAGNACAO | **PROGRESSO** | Fecha depois do senao, la no fim. |  |
| tese_18_busca_mensagem | E[10] | ESTAGNACAO | **PROGRESSO** | Tres, uma por numero. Mas a decisao precisa do achou pronto. |  |
| tese_18_busca_mensagem | E[12] | ESTAGNACAO | **PROGRESSO** | Depois de terminar, porque so ai eu sei que olhei todos. |  |
| tese_19_soma_do_indice | E[2] | ESTAGNACAO | **PROGRESSO** | A quantidade, tres numeros nas duas. Mas a soma tem que olhar os valores. |  |
| tese_19_soma_do_indice | E[4] | ESTAGNACAO | **PROGRESSO** | Aparece soma e aparece i. |  |
| tese_19_soma_do_indice | E[8] | ESTAGNACAO | **PROGRESSO** | Zero, um e dois. Sao as posicoes. |  |
| tese_19_soma_do_indice | E[10] | ESTAGNACAO | **PROGRESSO** | Tres. E foi o que apareceu nas duas vezes. Mas eu escrevi i porque e o que percorre o vetor. |  |
| tese_19_soma_do_indice | E[12] | ESTAGNACAO | **PROGRESSO** | E o lugar. O que esta la e outra coisa. |  |
| tese_20_primeira_ocorrencia | E[2] | ESTAGNACAO | **PROGRESSO** | O ultimo. Mas eu quero o primeiro. |  |
| tese_20_primeira_ocorrencia | E[4] | ESTAGNACAO | **PROGRESSO** | Tres vezes, uma para cada 7. |  |
| tese_20_primeira_ocorrencia | E[8] | ESTAGNACAO | **PROGRESSO** | E perdido. Mas eu preciso que ela seja escrita quando encontra. |  |
| tese_20_primeira_ocorrencia | E[10] | ESTAGNACAO | **PROGRESSO** | Que nao escrevesse. Mas o laco nao sabe se ja encontrou antes. |  |
| tese_20_primeira_ocorrencia | E[12] | ESTAGNACAO | **PROGRESSO** | E a propria posicao. Antes vale zero, que e o que eu uso para dizer que nao achou. |  |
| tese_21_conta_duplicado | E[2] | ESTAGNACAO | **PROGRESSO** | O 4 passa so no de dois. O 9 passa so no de tres. O 5 nao passa em nenhum. O 6 passa nos dois. |  |
| tese_21_conta_duplicado | E[4] | ESTAGNACAO | **PROGRESSO** | Tem dois incrementos, um em cada se. Mas cada se e uma pergunta diferente. |  |
| tese_21_conta_duplicado | E[8] | ESTAGNACAO | **PROGRESSO** | Duas. Uma em cada se. |  |
| tese_21_conta_duplicado | E[10] | ESTAGNACAO | **PROGRESSO** | Uma. Mas eu preciso dos dois testes para nao perder nem os pares nem os multiplos de tres. |  |
| tese_21_conta_duplicado | E[12] | ESTAGNACAO | **PROGRESSO** | Uma so. Mas se eu apagar um dos incrementos, o outro se fica sem contar nada. |  |
| tese_22_media_movel | E[2] | ESTAGNACAO | ESTAGNACAO | Nao sei. O laco percorre todos igual. | EST: 'Não sei' com observação que não avança (cf. 0_0 'Nao sei bem o que mais dizer aqui'). |
| tese_22_media_movel | E[4] | ESTAGNACAO | **PROGRESSO** | Depois da primeira da 1, depois da segunda da 2.5, depois da terceira da 4.25. |  |
| tese_22_media_movel | E[8] | ESTAGNACAO | **PROGRESSO** | Porque dividi por dois tendo somado so um valor. |  |
| tese_22_media_movel | E[10] | ESTAGNACAO | **PROGRESSO** | Tres vezes. E o 6 so uma. Por isso o ultimo pesa mais. |  |
| tese_22_media_movel | E[12] | ESTAGNACAO | **PROGRESSO** | Uma so, no fim. Mas o laco tem que ir calculando alguma coisa. |  |
| tese_23_incremento_duplo | E[2] | ESTAGNACAO | **PROGRESSO** | O 1 e o 3. Sao o primeiro e o terceiro. |  |
| tese_23_incremento_duplo | E[4] | ESTAGNACAO | **PROGRESSO** | Entraram o 0 e o 2, ficaram de fora o 1 e o 3. Ele so pega os pares. |  |
| tese_23_incremento_duplo | E[8] | ESTAGNACAO | **PROGRESSO** | O i mais mais no cabecalho do para. |  |
| tese_23_incremento_duplo | E[10] | ESTAGNACAO | **PROGRESSO** | A segunda linha faz i igual a i mais um. Mas eu pus isso para o laco andar. |  |
| tese_23_incremento_duplo | E[12] | ESTAGNACAO | **PROGRESSO** | O i mais mais do cabecalho. Entao tem duas coisas a andar. |  |
| tese_24_menor_aninhado | E[2] | ESTAGNACAO | **PROGRESSO** | valores[0], que e o 5. Entao o se do menor nunca rodou. |  |
| tese_24_menor_aninhado | E[4] | ESTAGNACAO | ESTAGNACAO | A do menor, que compara com valores[i]. Ela e verdadeira para o 4 e para o 3. | EST: responde à pergunta errada; o tutor corrige 'a minha pergunta é anterior'. Discutível: a afirmação factual que faz é verdadeira. |
| tese_24_menor_aninhado | E[8] | ESTAGNACAO | **PROGRESSO** | A do maior. O se do menor esta escrito dentro das chaves dela. |  |
| tese_24_menor_aninhado | E[10] | ESTAGNACAO | **PROGRESSO** | Nao, 4 nao e maior que 5. Entao nem entra. |  |
| tese_24_menor_aninhado | E[12] | ESTAGNACAO | **PROGRESSO** | Nao tem. Sao coisas opostas. Mas eu precisei aninhar para testar os dois no mesmo numero. |  |
| tese_25_contador_nao_reiniciado | E[2] | ESTAGNACAO | **PROGRESSO** | O segundo enquanto. Mas ele esta escrito ali, logo depois do primeiro. |  |
| tese_25_contador_nao_reiniciado | E[4] | ESTAGNACAO | **PROGRESSO** | i menor que n. E n vale 4. |  |
| tese_25_contador_nao_reiniciado | E[8] | ESTAGNACAO | **PROGRESSO** | O para da leitura, o i igual a zero antes do primeiro enquanto, e o i mais um dentro de cada um dos dois. |  |
| tese_25_contador_nao_reiniciado | E[10] | ESTAGNACAO | **PROGRESSO** | Quatro, porque ele para quando i chega a n. |  |
| tese_25_contador_nao_reiniciado | E[12] | ESTAGNACAO | **PROGRESSO** | Falsa. Entao ele nao entra nenhuma vez. Mas eu ja tinha posto i igual a zero. |  |
| tese_26_soma_quadrados | E[2] | ESTAGNACAO | **PROGRESSO** | De seis. E seis e 1 mais 2 mais 3. |  |
| tese_26_soma_quadrados | E[4] | ESTAGNACAO | **PROGRESSO** | A linha soma igual a soma vezes soma, depois do laco. Mas o enunciado pede quadrados, entao ela tem que existir. |  |
| tese_26_soma_quadrados | E[8] | ESTAGNACAO | **PROGRESSO** | Um por numero. Tres quadrados, no meu caso. |  |
| tese_26_soma_quadrados | E[10] | ESTAGNACAO | **PROGRESSO** | Um so, no fim. Mas se eu elevar cada um, onde ponho isso? |  |
| tese_26_soma_quadrados | E[12] | ESTAGNACAO | **PROGRESSO** | O laco, na linha que acumula. Mas essa linha so soma. |  |
