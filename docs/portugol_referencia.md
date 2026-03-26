# Referência da Linguagem Portugol (Portugol Webstudio)

## 1. Visão Geral

Portugol é uma linguagem de programação educacional similar à linguagem C, escrita em português. Foi desenvolvida para facilitar o aprendizado de lógica de programação em português, permitindo que iniciantes entendam conceitos de programação sem barreiras linguísticas.

O compilador Portugol verifica tanto a sintaxe quanto a semântica do código. A estrutura básica obrigatória de todo programa em Portugol é:

```portugol
programa {
  funcao inicio() {
    // Código do programa aqui
  }
}
```

## 2. Estrutura Básica do Programa

Todo programa em Portugol deve conter a estrutura acima. A função `inicio()` é o ponto de entrada do programa, onde a execução começa.

Comentários em Portugol podem ser feitos de duas formas:
- Comentário de linha única: `// comentário`
- Comentário de múltiplas linhas: `/* comentário */`

## 3. Tipos de Dados

### 3.1 Inteiro

O tipo `inteiro` armazena números inteiros positivos, negativos ou nulos.

**Sintaxe:**
```portugol
inteiro nome_da_variavel
inteiro variavel_inicializada = 42
```

**Descrição:** Armazena valores numéricos inteiros sem casas decimais.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro idade = 25
    inteiro quantidade = -10
    escreva(idade)
  }
}
```

### 3.2 Real

O tipo `real` armazena números reais com ponto decimal.

**Sintaxe:**
```portugol
real nome_da_variavel
real valor = 3.14
```

**Descrição:** Armazena valores numéricos com casas decimais. Importante: utiliza ponto (.) como separador decimal, não vírgula.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    real altura = 1.79
    real preco = 25.50
    escreva(altura)
  }
}
```

### 3.3 Caracter

O tipo `caracter` contém uma informação composta de apenas UM carácter alfanumérico ou especial.

**Sintaxe:**
```portugol
caracter nome_da_variavel
caracter vogal = 'a'
```

**Descrição:** Armazena um único caractere (letra, número, pontuação, etc.). O valor deve estar entre aspas simples.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    caracter vogal, consoante
    vogal = 'a'
    escreva("Digite uma consoante: ")
    leia(consoante)
    escreva("Vogal: ", vogal, "\n", "Consoante: ", consoante)
  }
}
```

### 3.4 Cadeia

O tipo `cadeia` é uma sequência ordenada de caracteres (símbolos).

**Sintaxe:**
```portugol
cadeia nome_da_variavel
cadeia texto = "Olá"
```

**Descrição:** Armazena textos ou sequências de caracteres. O valor deve estar entre aspas duplas.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    cadeia nome1, nome2
    nome1 = "Variável declarada através de atribuição"
    escreva("Digite seu nome: ")
    leia(nome2)
    escreva("\nOlá ", nome2)
  }
}
```

### 3.5 Lógico

O tipo `logico` contém um tipo de dado usado em operações lógicas, possuindo apenas dois valores: verdadeiro e falso.

**Sintaxe:**
```portugol
logico nome_da_variavel
logico resultado = verdadeiro
```

**Descrição:** Armazena valores booleanos (verdadeiro ou falso). Muito utilizado em operações relacionais e condicionais.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    logico teste
    inteiro num
    escreva("Digite um valor para ser comparado: ")
    leia(num)
    teste = (num > 0)
    escreva("O número digitado é maior que zero? ", teste)
  }
}
```

### 3.6 Vazio

`Vazio` é usado como tipo de retorno de uma função que não fornece um valor de resultado.

**Descrição:** Funções com tipo vazio são chamadas principalmente por seus efeitos colaterais (como realizar alguma tarefa ou escrever na saída). Terminam ao atingir o final da função ou executando um comando `retorne` sem valor.

**Exemplo:**
```portugol
programa {
  funcao vazio imprime_linha() {
    escreva("\n-----------------------------")
  }

  funcao vazio informacoes(cadeia nome, real versao, cadeia fornecedor) {
    se (nome == "Visual Basic") {
      retorne
    }
    escreva("\n")
    escreva("A linguagem ", nome)
    escreva(" encontra-se em sua versão ", versao)
    escreva(" e é fornecida pelo(a) ", fornecedor)
  }

  funcao inicio() {
    imprime_linha()
    informacoes("Portugol", 2.0, "UNIVALI")
  }
}
```

## 4. Declarações

### 4.1 Variáveis

Variáveis podem ser entendidas como apelidos para posições de memória. É através delas que os dados dos programas serão armazenados.

**Sintaxe:**
```portugol
tipo_dado nome_variavel
tipo_dado var1, var2, var3
tipo_dado variavel_inicializada = valor
```

**Descrição:**
- A sintaxe para declarar uma variável é: tipo da variável, nome da variável (ou das variáveis separadas por vírgula).
- Opcionalmente pode ser atribuído um valor de inicialização (exceto se for declarado mais de uma na mesma linha).
- Nome da variável deve ser explicativo.

**Exemplo:**
```portugol
programa {
  inteiro variavel

  funcao inicio() {
    inteiro outra_variavel
    real altura = 1.79
    cadeia frase = "Isso é uma variável do tipo cadeia"
    caracter inicial = 'P'
    logico exemplo = verdadeiro

    escreva(altura)
  }
}
```

### 4.2 Constantes

Constante é um identificador cujo valor associado não pode ser alterado pelo programa durante a sua execução.

**Sintaxe:**
```portugol
const tipo_dado NOME_CONSTANTE = valor
const inteiro VALOR_FIXO = 100
const real PI = 3.14159
```

**Descrição:**
- Use a palavra reservada `const` seguida do tipo de dado.
- Por convenção, nomes de constantes devem estar em CAIXA ALTA.
- O valor deve ser atribuído na declaração.

**Exemplo:**
```portugol
programa {
  const real ACELERACAO_GRAVIDADE = 9.78

  funcao inicio() {
    const caracter VOGAIS[5] = {'a', 'e', 'i', 'o', 'u'}
    const inteiro TECLADO_NUMERICO[][] = {{1,2,3}, {4,5,6}, {7,8,9}}
  }
}
```

### 4.3 Funções

Funções permitem agrupar um conjunto de instruções sob um nome, facilitando a reutilização de código.

**Sintaxe:**
```portugol
funcao tipo_retorno nome_funcao(parametro1, parametro2) {
  // Corpo da função
  retorne valor  // Se retorno não for vazio
}
```

**Descrição:**
- Usa palavra reservada `funcao`.
- Tipo de retorno é opcional (padrão é vazio).
- Suporta passagem por valor (padrão) e por referência (com `&`).
- Funções com retorno não-vazio precisam de `retorne`.

**Exemplo:**
```portugol
programa {
  funcao inteiro soma(inteiro a, inteiro b) {
    retorne a + b
  }

  funcao vazio exibir_resultado(inteiro resultado) {
    escreva("O resultado é: ", resultado)
  }

  funcao inicio() {
    inteiro res = soma(5, 3)
    exibir_resultado(res)
  }
}
```

### 4.4 Vetores

Um vetor pode ser visto como uma variável que possui diversas posições, armazenando diversos valores do mesmo tipo.

**Sintaxe:**
```portugol
tipo nome_vetor[tamanho]
tipo nome_vetor[] = {valor1, valor2, valor3}
```

**Descrição:**
- Elementos individuais são acessados por sua posição (índice).
- A primeira posição tem índice zero (0).
- Em um vetor de 10 elementos, os índices são 0 a 9.
- Tentar acessar um índice fora do tamanho declarado gera erro de execução.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro vetor[5] = {15, 22, 8, 10, 11}

    escreva(vetor[0], "\n")  // Imprime 15
    escreva(vetor[1], "\n")  // Imprime 22
    escreva(vetor[4], "\n")  // Imprime 11

    real outro_vetor[10]
    caracter nome[] = {'P', 'o', 'r', 't', 'u', 'g', 'o', 'l'}
  }
}
```

### 4.5 Matrizes

Uma matriz é definida como sendo um vetor com mais de uma dimensão (geralmente duas), armazenando dados de forma tabular (com linhas e colunas).

**Sintaxe:**
```portugol
tipo nome_matriz[linhas][colunas]
tipo nome_matriz[][] = {{val1, val2}, {val3, val4}}
```

**Descrição:**
- Todos os elementos são do mesmo tipo.
- Na declaração: tipo de dado, nome da variável, número de linhas, número de colunas (nesta ordem) entre colchetes.
- Para acessar um elemento: indicar dois índices (linha e coluna).

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro matriz[2][2] = {{15, 22}, {10, 11}}

    matriz[0][1] = -1

    inteiro i = 0
    escreva(matriz[i][0], "\n")  // Imprime 15
    escreva(matriz[1][1], "\n")  // Imprime 11

    real outra_matriz[2][4]
    caracter jogo_velha[][] = {{'X', 'O', 'X'}, {'O', 'X', 'O'}, {' ', ' ', 'X'}}
  }
}
```

## 5. Entrada e Saída

### 5.1 escreva

O comando `escreva` exibe dados ao usuário no console da IDE.

**Sintaxe:**
```portugol
escreva("Texto aqui")
escreva(variavel)
escreva("Texto", variavel, "Mais texto")
```

**Descrição:**
- Comando de saída de dados para a tela.
- Textos devem estar entre aspas duplas.
- Variáveis não devem estar entre aspas.
- Para múltiplas mensagens em sequência, separe com vírgulas.
- `\n` insere quebra de linha.
- `\t` insere tabulação.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro variavel = 5

    escreva("Escreva um texto aqui.\n")
    escreva(variavel, "\n")
    escreva(variavel + variavel, "\n")
    escreva("O valor da variável é: ", variavel)
    escreva("Texto com\n quebra-linha")
    escreva("Texto com\t tabulação")
  }
}
```

### 5.2 leia

O comando `leia` obtém informações do teclado do computador.

**Sintaxe:**
```portugol
leia(variavel)
leia(var1, var2, var3)
```

**Descrição:**
- Comando de entrada de dados via teclado.
- Aguarda um valor a ser digitado e o atribui diretamente na variável.
- A variável deve ter sido declarada anteriormente.
- Para múltiplas variáveis, separe com vírgulas.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro idade
    real salario, nota1, nota2, nota3
    cadeia nome, sobrenome

    escreva("Informe a sua idade: ")
    leia(idade)

    escreva("Informe seu salário: ")
    leia(salario)

    escreva("Informe o seu nome e sobrenome: ")
    leia(nome, sobrenome)

    escreva("Informe as suas três notas: ")
    leia(nota1, nota2, nota3)

    escreva("Seu nome é: ", nome, " ", sobrenome, "\n")
    escreva("Você tem ", idade, " anos e ganha de salário ", salario, "\n")
  }
}
```

### 5.3 limpa

O comando `limpa` limpa o console, removendo todo conteúdo exibido anteriormente.

**Sintaxe:**
```portugol
limpa()
```

**Descrição:**
- Não requer nenhum parâmetro.
- Não tem nenhuma saída.
- Útil para manter o console limpo e melhorar a visualização do programa.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    cadeia nome

    escreva("Qual é o seu nome?\n")
    leia(nome)

    limpa()

    escreva("Olá ", nome)
  }
}
```

## 6. Expressões e Operadores

### 6.1 Operação de Atribuição

A operação de atribuição serve para alterar o valor de uma variável.

**Sintaxe:**
```portugol
variavel = valor
variavel = variavel2
variavel = 6 + 4 / variavel2
```

**Descrição:**
- O sinal de igual "=" é o símbolo da atribuição.
- A variável à esquerda recebe o valor das operações à direita.
- Uma variável só pode receber atribuições do mesmo tipo.

**Operandos especiais:**
```portugol
variavel1 += variavel2   // Equivalente a: variavel1 = variavel1 + variavel2
variavel1 -= variavel2   // Equivalente a: variavel1 = variavel1 - variavel2
variavel1 *= variavel2   // Equivalente a: variavel1 = variavel1 * variavel2
variavel1 /= variavel2   // Equivalente a: variavel1 = variavel1 / variavel2
variavel1 %= variavel2   // Equivalente a: variavel1 = variavel1 % variavel2
variavel1 &= variavel2   // Equivalente a: variavel1 = variavel1 & variavel2
variavel1 ^= variavel2   // Equivalente a: variavel1 = variavel1 ^ variavel2
variavel1 |= variavel2   // Equivalente a: variavel1 = variavel1 | variavel2
variavel1++              // Equivalente a: variavel1 = variavel1 + 1
variavel1--              // Equivalente a: variavel1 = variavel1 - 1
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro a
    a = 2

    inteiro b
    leia(b)

    inteiro c
    c = b
  }
}
```

### 6.2 Operações Relacionais

As operações relacionais permitem realizar comparações que terão como resultado um valor lógico (verdadeiro ou falso).

**Operadores relacionais:**
| Operação | Símbolo |
|----------|---------|
| Maior    | >       |
| Menor    | <       |
| Maior ou igual | >= |
| Menor ou igual | <= |
| Igual    | ==      |
| Diferente | !=     |

**Exemplos de operações:**
| Operação | Resultado |
|----------|-----------|
| 3 > 4 | Falso |
| 7 != 7 | Falso |
| 9 == 10 - 1 | Verdadeiro |
| 33 <= 100 | Verdadeiro |
| 6 >= 5 + 1 | Verdadeiro |

**Sintaxe e uso:**
```portugol
se (5 > 3) {
  // Instruções
}

para (i = 0; i < 5; i++) {
  // Instruções
}
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro a = 5, b = 3

    se (a > b) {
      escreva("A é maior que B")
    }

    se (a == b) {
      escreva("A é igual a B")
    }

    se (a >= b) {
      escreva("A é maior ou igual a B")
    }
  }
}
```

### 6.3 Operações Aritméticas

#### 6.3.1 Adição (+)

Adição combina dois números em um único número (a soma).

**Sintaxe:**
```portugol
escreva(1 + 5)
real numero = 50 + 30
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| cadeia | cadeia | cadeia | "Oi" + " mundo" | "Oi mundo" |
| cadeia | caracter | cadeia | "Banan" + 'a' | "Banana" |
| cadeia | inteiro | cadeia | "Faz um" + 21 | "Faz um 21" |
| cadeia | real | cadeia | "Altura: " + 1.78 | "Altura: 1.78" |
| inteiro | inteiro | inteiro | 12 + 34 | 46 |
| inteiro | real | real | 76 + 3.25 | 79.25 |
| real | inteiro | real | 9.87 + 1 | 10.87 |
| real | real | real | 9.87 + 0.13 | 10.0 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro valor
    escreva(5 + 8, "\n")
    valor = 5 + 8
    escreva(valor)
  }
}
```

#### 6.3.2 Subtração (-)

Subtração indica quanto é um valor numérico se dele for removido outro valor.

**Sintaxe:**
```portugol
escreva(1 - 5)
real numero = 50 - 30
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 20 - 10 | 10 |
| inteiro | real | real | 90 - 0.5 | 89.5 |
| real | inteiro | real | 11.421 - 3 | 8.421 |
| real | real | real | 12.59 - 24.59 | -12.0 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro valor
    escreva(10 - 3, "\n")
    valor = 10 - 3
    escreva(valor)
  }
}
```

#### 6.3.3 Multiplicação (*)

Multiplicação é uma forma de adicionar uma quantidade finita de números iguais.

**Sintaxe:**
```portugol
escreva(1 * 5)
real numero = 50 * 30
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 6 * 8 | 48 |
| inteiro | real | real | 4 * 1.11 | 4.44 |
| real | inteiro | real | 6.712 * 174 | 1167.888 |
| real | real | real | 207.65 * 1.23 | 255.4095 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro valor
    escreva(3 * 4, "\n")
    valor = 3 * 4
    escreva(valor)
  }
}
```

#### 6.3.4 Divisão (/)

Divisão é a operação inversa da multiplicação, utilizada para dividir um valor em partes.

**Sintaxe:**
```portugol
escreva(15 / 5)
real numero = 50 / 25.6
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 5 / 2 | 2 |
| inteiro | real | real | 125 / 4.5 | 27.777777 |
| real | inteiro | real | 785.4 / 3 | 261.8 |
| real | real | real | 40.351 / 3.12 | 12.9333333 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro valor
    escreva(20 / 10, "\n")
    valor = 20 / 10
    escreva(valor)
  }
}
```

#### 6.3.5 Módulo (%)

Módulo encontra o resto da divisão de um número por outro.

**Sintaxe:**
```portugol
escreva(13 % 5)
real numero = 50 % 4
```

**Descrição:** Dados dois números a (dividendo) e b (divisor), a % b é o resto da divisão de a por b. Por exemplo: 7 % 3 = 1; 9 % 3 = 0.

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 45 % 7 | 3 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro valor
    escreva(7 % 3, "\n")
    valor = 7 % 3
    escreva(valor)
  }
}
```

### 6.4 Operações Lógicas

#### 6.4.1 Operador E (e)

O resultado de uma operação lógica com 'e' é verdadeiro somente quando AMBOS os operandos forem verdadeiros.

**Tabela Verdade:**
| Operação 1 | Operação 2 | Resultado |
|-----------|-----------|-----------|
| Verdadeiro | Verdadeiro | Verdadeiro |
| Verdadeiro | Falso | Falso |
| Falso | Verdadeiro | Falso |
| Falso | Falso | Falso |

**Sintaxe:**
```portugol
se (5 > 4 e 6 == 6) {
  // Instruções
}

logico saida = 5 > 3 e 4 < 5 e 6 < 7
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro a = 2, b = 2

    se (a == 2 e b == 2) {
      escreva("Teste positivo")
    }

    inteiro c = 2, d = 3
    se (c == 2 e d == 2) {
      escreva("Teste positivo")
    }

    inteiro g = 2, f = 2
    se (g == 2 e f != 3) {
      escreva("Teste positivo")
    }
  }
}
```

#### 6.4.2 Operador OU (ou)

O resultado de uma operação lógica com 'ou' é verdadeiro sempre que UM dos operandos for verdadeiro.

**Tabela Verdade:**
| Operação 1 | Operação 2 | Resultado |
|-----------|-----------|-----------|
| Verdadeiro | Verdadeiro | Verdadeiro |
| Verdadeiro | Falso | Verdadeiro |
| Falso | Verdadeiro | Verdadeiro |
| Falso | Falso | Falso |

**Sintaxe:**
```portugol
se (5 > 4 ou 7 == 6) {
  // Instruções
}

logico saida = 5 > 8 ou 4 < 12 ou 34 < 7
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro a = 2, b = 2

    se (a == 2 ou b == 2) {
      escreva("Teste positivo")
    }

    inteiro c = 2, d = 3
    se (c == 2 ou d == 2) {
      escreva("Teste positivo")
    }
  }
}
```

#### 6.4.3 Operador NÃO (nao)

O operador 'nao' funciona de forma diferente pois necessita apenas de um operando. Quando usado, o valor lógico do operando é invertido.

**Sintaxe:**
```portugol
se (nao falso) {
  // Instruções
}

logico saida = nao (5 > 3 e 4 < 5) e 6 < 7
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    logico teste = falso

    se (nao(teste)) {
      escreva("Teste positivo")
    }

    inteiro a = 2, b = 3
    se (nao(a + b > 7)) {
      escreva("Teste positivo")
    }
  }
}
```

### 6.5 Operações Bitwise

#### 6.5.1 Bitwise AND (&)

Semelhante ao operador lógico 'e', devolvendo 1 quando ambos operandos forem '1'.

**Tabela Verdade:**
| B | A | S |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |

**Sintaxe:**
```portugol
inteiro resultado = 5 & 3  // 0101 AND 0011 = 0001 (decimal 1)
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 6 & 13 | 4 |

**Nota:** Operadores bitwise só trabalham com números do tipo Inteiro.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    escreva(5 & 3)
  }
}
```

#### 6.5.2 Bitwise OR (|)

Devolvendo 1 sempre que pelo menos um dos operandos seja '1'.

**Tabela Verdade:**
| B | A | S |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 1 |

**Sintaxe:**
```portugol
inteiro resultado = 5 | 3  // 0101 OR 0011 = 0111 (decimal 7)
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 2 | 8 | 10 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    escreva(5 | 3)
  }
}
```

#### 6.5.3 Bitwise NOT (~)

Operador unário que inverte os bits.

**Tabela Verdade:**
| A | S |
|---|---|
| 0 | 1 |
| 1 | 0 |

**Sintaxe:**
```portugol
inteiro resultado = ~7  // 0111 NOT = 1000 (decimal 8)
```

**Tabela de compatibilidade:**
| Operando | Resultado | Exemplo | Resultado |
|----------|-----------|---------|-----------|
| inteiro | inteiro | ~1 | -2 |

**Nota:** É importante compreender o conceito de "Complemento de dois".

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    escreva(~7)
  }
}
```

#### 6.5.4 Bitwise XOR (^)

Devolvendo 1 sempre que o número de operandos iguais a 1 for ímpar.

**Tabela Verdade:**
| B | A | S |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 0 |

**Sintaxe:**
```portugol
inteiro resultado = 5 ^ 3  // 0101 XOR 0011 = 0110 (decimal 6)
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 2 ^ 10 | 8 |

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    escreva(5 ^ 3)
  }
}
```

#### 6.5.5 Bitwise Shift (>> e <<)

Os operadores de Shift deslocam bits de um número inteiro para direita ou para a esquerda.

**Left Shift (<<):** Bits são deslocados para a esquerda e zeros acrescentados à direita.

**Sintaxe:**
```portugol
inteiro resultado = 23 << 1  // 00010111 LEFT-SHIFT = 00101110 (decimal 46)
```

**Right Shift (>>):** Bit de sinal é deslocado da esquerda, preservando o sinal do operando.

**Sintaxe:**
```portugol
inteiro resultado = -105 >> 1  // 10010111 RIGHT-SHIFT = 11001011 (decimal -53)
```

**Tabela de compatibilidade:**
| Operando Esquerdo | Operando Direito | Resultado | Exemplo | Resultado |
|-------------------|------------------|-----------|---------|-----------|
| inteiro | inteiro | inteiro | 12 >> 2 | 3 |
| inteiro | inteiro | inteiro | 12 << 2 | 48 |

**Notas:**
- Left Shift equivale a multiplicar por 2 para cada deslocamento.
- Right Shift equivale a dividir por 2 para cada deslocamento.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    escreva(23 << 1, "\n", -105 >> 1)
  }
}
```

## 7. Estruturas de Controle

### 7.1 Desvios Condicionais

#### 7.1.1 se

O desvio condicional simples permite executar um conjunto de instruções apenas se uma condição for verdadeira.

**Sintaxe:**
```portugol
se (condicao) {
  // Instruções a serem executadas se verdadeiro
}
```

**Descrição:** Se o teste lógico resultar verdadeiro, as instruções dentro das chaves serão executadas. Se falso, o algoritmo pula o trecho.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro num
    escreva("Digite um número: ")
    leia(num)

    se (num == 0) {
      escreva("O número digitado é 0")
    }
  }
}
```

#### 7.1.2 se-senao

Executa um conjunto de instruções se a condição for verdadeira, e outro conjunto se for falsa.

**Sintaxe:**
```portugol
se (condicao) {
  // Instruções se verdadeiro
} senao {
  // Instruções se falso
}
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro hora
    escreva("Digite a hora: ")
    leia(hora)

    se (hora >= 6 e hora <= 18) {
      escreva("É dia")
    } senao {
      escreva("É noite")
    }
  }
}
```

#### 7.1.3 se-senao se

Permite verificar múltiplas condições em sequência.

**Sintaxe:**
```portugol
se (condicao1) {
  // Instruções se condicao1 for verdadeira
} senao se (condicao2) {
  // Instruções se condicao1 for falsa e condicao2 for verdadeira
} senao {
  // Instruções se todas anteriores forem falsas
}
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    real nota
    leia(nota)

    se (nota >= 9) {
      escreva("O aluno teve um desempenho muito bom")
    } senao se (nota >= 7) {
      escreva("O aluno teve um desempenho bom")
    } senao se (nota >= 6) {
      escreva("O aluno teve um desempenho razoável")
    } senao {
      escreva("O aluno teve um desempenho mau")
    }
  }
}
```

#### 7.1.4 escolha-caso

Reduz a complexidade quando há múltiplos testes de valor específico.

**Sintaxe:**
```portugol
escolha (expressao) {
  caso valor1:
    // Instruções
    pare
  caso valor2:
    // Instruções
    pare
  caso contrario:
    // Instruções
}
```

**Descrição:**
- Não é possível usar operadores lógicos, apenas valores específicos.
- O comando `pare` impede que os blocos seguintes sejam executados.
- O `caso contrario` é executado se nenhum caso anterior for verdadeiro.

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro valor = 1

    escolha (valor) {
      caso 0:
        escreva("O valor é igual a 0")
        pare
      caso 1:
        escreva("O valor é igual a 1")
        pare
      caso 2:
        escreva("O valor é igual a 2")
        pare
      caso contrario:
        escreva("O valor não é 0, 1 ou 2")
    }
  }
}
```

### 7.2 Laços de Repetição

#### 7.2.1 enquanto (pré-testado)

Executa uma lista de comandos enquanto uma condição for verdadeira. A condição é testada ANTES de cada iteração.

**Sintaxe:**
```portugol
enquanto (condicao) {
  // Instruções
}
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    caracter parar
    parar = 'N'

    enquanto (parar != 'S') {
      escreva("Deseja parar o laço? (S/N): ")
      leia(parar)
    }
  }
}
```

#### 7.2.2 faca-enquanto (pós-testado)

Executa uma lista de comandos e depois verifica a condição. As instruções sempre são executadas pelo menos uma vez.

**Sintaxe:**
```portugol
faca {
  // Instruções
} enquanto (condicao)
```

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    real aresta, area

    faca {
      escreva("Informe o valor da aresta: ")
      leia(aresta)
    } enquanto (aresta <= 0)

    area = aresta * aresta
    escreva("A área é: ", area)
  }
}
```

#### 7.2.3 para (com variável de controle)

Facilita a construção de algoritmos com número definido de repetições, com contador embutido.

**Sintaxe:**
```portugol
para (inteiro i = 0; i < 10; i++) {
  // Instruções
}
```

**Partes:**
1. Inicialização da variável contadora
2. Condição a ser testada
3. Incremento/alteração da variável de controle

**Exemplo:**
```portugol
programa {
  funcao inicio() {
    inteiro tab

    para (inteiro c = 1; c <= 10; c++) {
      tab = c * 3
      escreva("3 x ", c, " = ", tab, "\n")
    }
  }
}
```

## 8. Bibliotecas

As bibliotecas em Portugol fornecem funções e constantes pré-definidas para facilitar o desenvolvimento de programas. Elas cobrem diversas áreas como calendário, gráficos, matemática, texto, tipos e utilitários.

### 8.1 Biblioteca Calendario

Fornece funções e constantes para trabalhar com datas e horários.

**Constantes de Dia da Semana:**
- `DIA_DOMINGO` = 1
- `DIA_SEGUNDA_FEIRA` = 2
- `DIA_TERCA_FEIRA` = 3
- `DIA_QUARTA_FEIRA` = 4
- `DIA_QUINTA_FEIRA` = 5
- `DIA_SEXTA_FEIRA` = 6
- `DIA_SABADO` = 7

**Constantes de Mês:**
- `MES_JANEIRO`, `MES_FEVEREIRO`, `MES_MARCO`, `MES_ABRIL`, `MES_MAIO`, `MES_JUNHO`
- `MES_JULHO`, `MES_AGOSTO`, `MES_SETEMBRO`, `MES_OUTUBRO`, `MES_NOVEMBRO`, `MES_DEZEMBRO`

**Funções principais:**
- `ano_atual()`: Recupera o ano atual
- `mes_atual()`: Recupera o mês atual
- `dia_mes_atual()`: Recupera o dia do mês
- `dia_semana_atual()`: Recupera o dia da semana (número)
- `dia_semana_completo()`: Retorna nome completo do dia
- `hora_atual()`: Recupera a hora atual
- `minuto_atual()`: Recupera os minutos
- `segundo_atual()`: Recupera os segundos
- `milisegundo_atual()`: Recupera milissegundos

### 8.2 Biblioteca Graficos

Fornece funções e constantes para trabalhar com gráficos e cores.

**Constantes de Cor:**
- `COR_VERMELHO`
- `COR_VERDE`
- `COR_AZUL`
- `COR_AMARELO`
- `COR_BRANCO`
- `COR_PRETO`

**Constantes de Canais RGB:**
- `CANAL_R` (Vermelho)
- `CANAL_G` (Verde)
- `CANAL_B` (Azul)

**Constantes de Gradiente:**
- `GRADIENTE_ACIMA`
- `GRADIENTE_ABAIXO`
- `GRADIENTE_ESQUERDA`
- `GRADIENTE_DIREITA`
- `GRADIENTE_SUPERIOR_ESQUERDO`
- `GRADIENTE_SUPERIOR_DIREITO`
- `GRADIENTE_INFERIOR_ESQUERDO`
- `GRADIENTE_INFERIOR_DIREITO`

**Funções principais:**
- `altura_janela()`: Obtém a altura da janela
- `largura_janela()`: Obtém a largura da janela
- `altura_imagem()`: Obtém altura de uma imagem

### 8.3 Biblioteca Matematica

Fornece constantes e funções matemáticas.

**Constantes:**
- `PI` = 3.141592653589793

**Funções principais:**
- `arredondar(real numero, inteiro casas)`: Arredonda para número de casas decimais
- `seno(real angulo)`: Calcula o seno
- `cosseno(real angulo)`: Calcula o cosseno
- `tangente(real angulo)`: Calcula a tangente
- `raiz_quadrada(real numero)`: Calcula raiz quadrada
- `potencia(real base, real expoente)`: Calcula potência
- `valor_absoluto(real numero)`: Retorna valor absoluto
- `minimo(real a, real b)`: Retorna o menor valor
- `maximo(real a, real b)`: Retorna o maior valor

### 8.4 Biblioteca Texto

Fornece funções para manipulação de strings.

**Funções principais:**
- `caixa_alta(cadeia cad)`: Converte para maiúsculas
- `caixa_baixa(cadeia cad)`: Converte para minúsculas
- `extrair_subtexto(cadeia cad, inteiro pos_inicial, inteiro pos_final)`: Extrai parte da string
- `comprimento(cadeia cad)`: Retorna tamanho da string
- `substituir(cadeia cad, cadeia antiga, cadeia nova)`: Substitui texto
- `contem(cadeia cad, cadeia texto)`: Verifica se contém
- `indice_de(cadeia cad, cadeia texto)`: Encontra posição

### 8.5 Biblioteca Tipos

Fornece funções para verificação e conversão de tipos.

**Funções principais:**
- `cadeia_e_caracter(cadeia cad)`: Verifica se é caracter
- `cadeia_e_inteiro(cadeia cad, inteiro base)`: Verifica se é inteiro
- `cadeia_e_logico(cadeia cad)`: Verifica se é lógico
- `cadeia_e_real(cadeia cad)`: Verifica se é real
- `caracter_para_codigo(caracter c)`: Converte caracter para código ASCII

### 8.6 Biblioteca Util

Fornece funções utilitárias.

**Funções principais:**
- `aguarde(inteiro intervalo)`: Pausa execução por milissegundos
- `numero_elementos(vetor[])`: Retorna quantidade de elementos do vetor
- `numero_linhas(matriz[][])`: Retorna número de linhas
- `numero_colunas(matriz[][])`: Retorna número de colunas
- `limpar_buffer()`: Limpa buffer de entrada

---

**Documento gerado:** Março de 2026
**Versão:** 1.0 - Referência Completa do Portugol