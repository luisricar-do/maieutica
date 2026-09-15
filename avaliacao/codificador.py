r"""Ferramenta local de codificação da validação humana (Capítulo 5).

Entrada de dados, não análise. Apresenta um turno de cada vez e grava as colunas de codificação
em ``codificacao.csv`` / ``recodificacao.csv``. Existe porque abrir essas planilhas numa folha de
cálculo reescreve quebras de linha, aspas e encoding: os campos de contexto trazem código-fonte e
conversas inteiras com ``\n`` dentro de campos citados — 8.464 linhas físicas para 210 registros —
e um registro partido é confiabilidade perdida, não formatação perdida.

O arquivo é reescrito por inteiro a cada gravação, com ``csv.writer`` no dialeto ``excel``, o
mesmo que gerou as planilhas: ``\r\n`` entre registros, ``\n`` preservado dentro dos campos,
``QUOTE_MINIMAL`` e aspas duplicadas. Depois de ``fsync``, ``os.replace`` troca o temporário pelo
definitivo — ou a gravação acontece inteira, ou não acontece. Abrir e gravar sem editar devolve o
arquivo byte a byte igual ao original, e ``tests/test_validacao_codificador.py`` prova-o.

**Cegueira — invariante, não preferência.** O codificador é cego à condição e ao veredito do juiz
(``metodologia.tex``). Este módulo lê exclusivamente as duas planilhas, ``procedimento.json`` e as
*chaves* de ``mapa_recodificacao.json``; não abre ``juizos.jsonl``, ``turnos.jsonl``,
``avaliacao/banco/`` nem ``mapa_amostra.json`` — este último cifra a condição no próprio valor
(``…|B|2``) e desfaria a cegueira sozinho. De ``mapa_recodificacao.json`` só as chaves são usadas,
para a ordem: os valores ligam cada item à sua identidade na primeira rodada e deixariam consultar
o que já se respondeu. Ao navegador só chegam as colunas de :data:`CAMPOS_CONTEXTO`, montadas por
lista branca — coluna nova na planilha não vaza por omissão. Nenhum caminho proibido aparece neste
arquivo, e é assim que a cegueira se audita: por leitura dele, sem seguir importações.

Uso::

    python -m avaliacao.codificador                          # primeira rodada
    python -m avaliacao.codificador --rodada recodificacao   # terço diferido
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import tempfile
import threading
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DIRETORIO_PADRAO = Path("avaliacao/execucoes/cap5/validacao_humana")
ARQUIVO_PROCEDIMENTO = "procedimento.json"
ARQUIVO_MAPA_RECODIFICACAO = "mapa_recodificacao.json"
ARQUIVO_DA_RODADA = {
    "primeira": "codificacao.csv",
    "recodificacao": "recodificacao.csv",
}

#: Colunas de leitura que chegam ao navegador. Lista branca: o que não está aqui não é servido.
CAMPOS_CONTEXTO = (
    "id_cego",
    "item_id",
    "tipo_bug",
    "enunciado",
    "codigo_no_prefixo",
    "erros_no_prefixo",
    "conversa_ate_aqui",
    "turno_do_tutor",
)
#: Campos onde a indentação e as quebras de linha são o dado: monoespaçado e ``pre-wrap``.
CAMPOS_LONGOS = (
    "codigo_no_prefixo",
    "erros_no_prefixo",
    "conversa_ate_aqui",
    "turno_do_tutor",
)

#: Domínio de cada variável, na ordem em que aparece na planilha. É esta tabela que valida no
#: servidor e, servida como JSON à página, valida também no cliente — uma fonte só.
#:
#: ``ancorado`` não é booleano: o juiz emite ``sim``/``nao``/``alvo_errado``
#: (``avaliacao/juiz.py``) e ``validacao_humana._valor`` compara a resposta humana com a dele como
#: string em minúsculas. Gravar ``0``/``1`` aqui zeraria o κ humano×juiz da variável por
#: construção e tornaria ``alvo_errado`` — ancorado no alvo errado — impossível de registrar.
DOMINIOS: dict[str, tuple[str, ...]] = {
    "diretividade": ("0", "1", "2", "3"),
    "fidelidade": ("1", "2", "3"),
    "movimento_estudante": (
        "PROGRESSO",
        "ESTAGNACAO",
        "REGRESSAO",
        "PEDIDO_EXPLICITO",
        "NENHUM",
    ),
    "ancorado": ("sim", "nao", "alvo_errado"),
    "irrelevante": ("0", "1"),
    "repetida": ("0", "1"),
    "excessivamente_direta": ("0", "1"),
    "prematura": ("0", "1"),
    "incorreta": ("0", "1"),
}
CAMPO_LIVRE = "notas"
CAMPOS_CODIFICAVEIS = (*DOMINIOS, CAMPO_LIVRE)


def escrever_atomico(caminho: Path, dados: bytes) -> None:
    """Grava ``dados`` em ``caminho`` sem estado intermediário visível.

    Temporário no mesmo diretório (``os.replace`` só é atômico dentro do mesmo sistema de
    arquivos), ``fsync`` antes da troca e ``fsync`` do diretório depois, para que o rename
    sobreviva a uma queda de energia. Falhando qualquer passo, o temporário é removido e o
    arquivo original fica intacto.
    """
    descritor, temporario = tempfile.mkstemp(
        dir=caminho.parent, prefix=f".{caminho.name}.", suffix=".parcial"
    )
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
    try:
        diretorio = os.open(caminho.parent, os.O_RDONLY)
        try:
            os.fsync(diretorio)
        finally:
            os.close(diretorio)
    except OSError:
        pass  # Sistemas de arquivos que recusam fsync de diretório; o conteúdo já está em disco.


def ordem_da_rodada(diretorio: Path, rodada: str) -> list[str]:
    """Os ``id_cego`` na ordem de apresentação da rodada."""
    if rodada == "primeira":
        procedimento = json.loads(
            (diretorio / ARQUIVO_PROCEDIMENTO).read_text(encoding="utf-8")
        )
        return list(procedimento["ordem_primeira_rodada"])
    mapa = json.loads(
        (diretorio / ARQUIVO_MAPA_RECODIFICACAO).read_text(encoding="utf-8")
    )
    return list(mapa)  # Só as chaves: os valores de-cegariam a rodada.


class Planilha:
    """A planilha em memória, reescrita por inteiro a cada gravação."""

    def __init__(self, caminho: Path, ordem: list[str]) -> None:
        self.caminho = caminho
        with caminho.open(encoding="utf-8", newline="") as arquivo:
            linhas = list(csv.reader(arquivo))
        if not linhas:
            raise SystemExit(f"{caminho} está vazio.")
        self.cabecalho, self.registros = linhas[0], linhas[1:]
        ausentes = [
            coluna
            for coluna in (*CAMPOS_CONTEXTO, *CAMPOS_CODIFICAVEIS)
            if coluna not in self.cabecalho
        ]
        if ausentes:
            raise SystemExit(
                f"{caminho.name} não tem as colunas: {', '.join(ausentes)}."
            )
        self.coluna = {nome: posicao for posicao, nome in enumerate(self.cabecalho)}
        identificador = self.coluna["id_cego"]
        posicoes = {
            registro[identificador]: i for i, registro in enumerate(self.registros)
        }
        self.ordem = [posicoes[id_cego] for id_cego in ordem if id_cego in posicoes]
        if len(self.ordem) != len(self.registros):
            raise SystemExit(
                f"a ordem da rodada cobre {len(self.ordem)} dos {len(self.registros)} "
                f"registros de {caminho.name}: planilha e procedimento não são do mesmo sorteio."
            )

    def valor(self, posicao: int, campo: str) -> str:
        return self.registros[posicao][self.coluna[campo]]

    def codificado(self, posicao: int) -> bool:
        """Codificado é ter todas as variáveis preenchidas; ``notas`` é opcional."""
        return all(self.valor(posicao, campo).strip() for campo in DOMINIOS)

    def primeiro_pendente(self) -> int:
        for indice, posicao in enumerate(self.ordem):
            if not self.codificado(posicao):
                return indice
        return max(len(self.ordem) - 1, 0)

    def concluida(self) -> bool:
        return all(self.codificado(posicao) for posicao in self.ordem)

    def aplicar(self, posicao: int, valores: dict[str, str]) -> None:
        registro = self.registros[posicao]
        for campo, valor in valores.items():
            registro[self.coluna[campo]] = valor

    def bytes_csv(self) -> bytes:
        """O arquivo inteiro como bytes, no dialeto que o gerou."""
        memoria = io.StringIO(newline="")
        escritor = csv.writer(
            memoria
        )  # excel: \r\n entre registros, QUOTE_MINIMAL, aspas dobradas
        escritor.writerow(self.cabecalho)
        escritor.writerows(self.registros)
        return memoria.getvalue().encode("utf-8")

    def gravar(self) -> None:
        escrever_atomico(self.caminho, self.bytes_csv())


def validar(enviados: dict) -> tuple[dict[str, str], list[str]]:
    """Confere os valores contra :data:`DOMINIOS`. Devolve ``(valores, erros)``."""
    valores: dict[str, str] = {}
    erros: list[str] = []
    for campo, dominio in DOMINIOS.items():
        bruto = str(enviados.get(campo, "") or "").strip()
        if not bruto:
            erros.append(f"{campo}: em branco")
        elif bruto not in dominio:
            erros.append(f"{campo}: '{bruto}' fora de {{{', '.join(dominio)}}}")
        else:
            valores[campo] = bruto
    notas = enviados.get(CAMPO_LIVRE) or ""
    # O navegador pode devolver CRLF numa textarea; dentro dos campos a planilha usa LF.
    valores[CAMPO_LIVRE] = str(notas).replace("\r\n", "\n").replace("\r", "\n")
    return valores, erros


def marcar_rodada(caminho: Path, rodada: str, chave: str, quando: str) -> None:
    """Grava ``iniciada_em``/``concluida_em`` da rodada, uma vez, em ``procedimento.json``.

    O pré-registro promete publicar a data de cada rodada e o arquivo gerado não tinha campo para
    ela. Marca-se ``iniciada_em`` na primeira gravação — abrir a ferramenta para espreitar não é
    começar a codificar — e ``concluida_em`` na gravação que fecha a última pendência. Nenhuma das
    duas é reescrita depois: revisar um registro não muda a data em que a rodada correu.
    """
    procedimento = json.loads(caminho.read_text(encoding="utf-8"))
    registro = procedimento.setdefault("rodadas", {}).setdefault(rodada, {})
    if registro.get(chave):
        return
    registro[chave] = quando
    escrever_atomico(
        caminho,
        (json.dumps(procedimento, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


class Servico:
    """Estado partilhado entre conexões. O cadeado serializa ler-modificar-gravar."""

    def __init__(self, planilha: Planilha, procedimento: Path, rodada: str) -> None:
        self.planilha = planilha
        self.procedimento = procedimento
        self.rodada = rodada
        self.cadeado = threading.Lock()

    def estado(self, indice: int) -> dict:
        planilha = self.planilha
        indice = max(0, min(indice, len(planilha.ordem) - 1))
        posicao = planilha.ordem[indice]
        return {
            "indice": indice,
            "total": len(planilha.ordem),
            "codificados": sum(1 for p in planilha.ordem if planilha.codificado(p)),
            "rodada": self.rodada,
            "arquivo": planilha.caminho.name,
            "codificado": planilha.codificado(posicao),
            # Lista branca: só estas colunas saem daqui.
            "registro": {
                campo: planilha.valor(posicao, campo) for campo in CAMPOS_CONTEXTO
            },
            "codificacao": {
                campo: planilha.valor(posicao, campo) for campo in CAMPOS_CODIFICAVEIS
            },
        }

    def gravar(self, indice: int, enviados: dict) -> tuple[dict, int]:
        valores, erros = validar(enviados)
        if erros:
            return {"erros": erros}, 422
        with self.cadeado:
            planilha = self.planilha
            if not 0 <= indice < len(planilha.ordem):
                return {"erros": ["índice fora da rodada"]}, 400
            planilha.aplicar(planilha.ordem[indice], valores)
            planilha.gravar()
            agora = datetime.now(UTC).isoformat()
            marcar_rodada(self.procedimento, self.rodada, "iniciada_em", agora)
            if planilha.concluida():
                marcar_rodada(self.procedimento, self.rodada, "concluida_em", agora)
            return self.estado(min(indice + 1, len(planilha.ordem) - 1)), 200


def criar_manipulador(servico: Servico) -> type[BaseHTTPRequestHandler]:
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "codificador"

        def log_message(self, *_: object) -> None:  # noqa: D102 - o terminal é do codificador.
            pass

        def _responder(self, corpo: bytes, tipo: str, codigo: int = 200) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, dados: dict, codigo: int = 200) -> None:
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self._responder(corpo, "application/json; charset=utf-8", codigo)

        def do_GET(self) -> None:  # noqa: N802 - assinatura de BaseHTTPRequestHandler.
            rota = urlparse(self.path)
            if rota.path == "/":
                inicial = servico.planilha.primeiro_pendente()
                return self._responder(pagina(inicial), "text/html; charset=utf-8")
            if rota.path == "/api/estado":
                bruto = parse_qs(rota.query).get("indice", ["0"])[0]
                try:
                    indice = int(bruto)
                except ValueError:
                    indice = 0
                return self._json(servico.estado(indice))
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - assinatura de BaseHTTPRequestHandler.
            if urlparse(self.path).path != "/api/gravar":
                return self.send_error(404)
            tamanho = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                indice = int(corpo.get("indice"))
            except (json.JSONDecodeError, TypeError, ValueError):
                return self._json({"erros": ["requisição inválida"]}, 400)
            resposta, codigo = servico.gravar(indice, corpo.get("valores") or {})
            self._json(resposta, codigo)

    return Manipulador


def pagina(inicial: int) -> bytes:
    """A página com os domínios injetados, para cliente e servidor validarem a mesma tabela.

    ``inicial`` é o registro em que a rodada retoma — o primeiro por codificar.
    """
    return (
        MODELO.replace("__INICIAL__", str(inicial))
        .replace("__DOMINIOS__", json.dumps(DOMINIOS, ensure_ascii=False))
        .replace("__CONTEXTO__", json.dumps(CAMPOS_CONTEXTO))
        .replace("__LONGOS__", json.dumps(CAMPOS_LONGOS))
        .replace("__LIVRE__", json.dumps(CAMPO_LIVRE))
        .encode("utf-8")
    )


def principal(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        prog="codificador", description="Codificação da validação humana do Capítulo 5."
    )
    analisador.add_argument(
        "--rodada", choices=tuple(ARQUIVO_DA_RODADA), default="primeira"
    )
    analisador.add_argument("--diretorio", type=Path, default=DIRETORIO_PADRAO)
    analisador.add_argument("--porta", type=int, default=8765)
    analisador.add_argument("--sem-navegador", action="store_true")
    opcoes = analisador.parse_args(argumentos)

    diretorio = opcoes.diretorio
    planilha = Planilha(
        diretorio / ARQUIVO_DA_RODADA[opcoes.rodada],
        ordem_da_rodada(diretorio, opcoes.rodada),
    )
    servico = Servico(planilha, diretorio / ARQUIVO_PROCEDIMENTO, opcoes.rodada)

    endereco = ("127.0.0.1", opcoes.porta)
    servidor = ThreadingHTTPServer(endereco, criar_manipulador(servico))
    servidor.daemon_threads = True
    url = f"http://{endereco[0]}:{servidor.server_port}/"

    pendente = planilha.primeiro_pendente()
    codificados = sum(1 for posicao in planilha.ordem if planilha.codificado(posicao))
    print(f"rodada {opcoes.rodada} · {planilha.caminho}")
    print(
        f"{codificados}/{len(planilha.ordem)} codificados · retomando no registro {pendente + 1}"
    )
    print(f"{url}  (Ctrl+C para encerrar)")
    if not opcoes.sem_navegador:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")
    finally:
        servidor.server_close()
    return 0


MODELO = """<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codificação — validação humana</title>
<style>
  :root {
    --fundo: #fbfaf8; --painel: #fff; --borda: #e3e0da; --texto: #23211e;
    --suave: #6f6a62; --marca: #2f5d50; --alerta: #9c2f2f;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --fundo: #1a1917; --painel: #232120; --borda: #3a3733; --texto: #eceae6;
      --suave: #a09a91; --marca: #7fb8a5; --alerta: #e08585;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--fundo); color: var(--texto);
    font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", system-ui, sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 5; background: var(--painel);
    border-bottom: 1px solid var(--borda); padding: 10px 20px;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  header .id { font: 600 17px ui-monospace, SFMono-Regular, Menlo, monospace; }
  header .meta { color: var(--suave); font-size: 13px; }
  .barra { flex: 1 1 160px; height: 6px; background: var(--borda); border-radius: 3px; min-width: 120px; }
  .barra > i { display: block; height: 100%; background: var(--marca); border-radius: 3px; }
  .selo { font-size: 12px; padding: 2px 8px; border-radius: 10px; border: 1px solid var(--borda); color: var(--suave); }
  main { max-width: 1060px; margin: 0 auto; padding: 20px 20px 96px; }
  section { background: var(--painel); border: 1px solid var(--borda); border-radius: 8px; margin-bottom: 14px; }
  section > h2 {
    margin: 0; padding: 9px 14px; font-size: 11px; letter-spacing: .09em; text-transform: uppercase;
    color: var(--suave); border-bottom: 1px solid var(--borda); font-weight: 600;
  }
  .corpo { padding: 12px 14px; }
  pre.corpo {
    margin: 0; white-space: pre-wrap; overflow-wrap: anywhere;
    font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .campo { padding: 11px 14px; border-bottom: 1px solid var(--borda); display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; }
  .campo:last-child { border-bottom: 0; }
  .campo > label:first-child { flex: 0 0 190px; font-size: 13px; font-weight: 600; }
  .opcoes { display: flex; gap: 6px; flex-wrap: wrap; }
  .opcoes input { position: absolute; opacity: 0; pointer-events: none; }
  .opcoes span {
    display: inline-block; padding: 4px 11px; border: 1px solid var(--borda); border-radius: 6px;
    cursor: pointer; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; user-select: none;
  }
  .opcoes input:checked + span { background: var(--marca); border-color: var(--marca); color: #fff; }
  .opcoes input:focus-visible + span { outline: 2px solid var(--marca); outline-offset: 2px; }
  textarea {
    flex: 1 1 320px; min-height: 62px; padding: 8px; border: 1px solid var(--borda); border-radius: 6px;
    background: var(--fundo); color: var(--texto); font: 13px/1.5 ui-sans-serif, system-ui, sans-serif; resize: vertical;
  }
  footer {
    position: fixed; left: 0; right: 0; bottom: 0; background: var(--painel);
    border-top: 1px solid var(--borda); padding: 10px 20px; display: flex; gap: 10px;
    align-items: center; justify-content: flex-end; flex-wrap: wrap;
  }
  button {
    padding: 8px 15px; border-radius: 6px; border: 1px solid var(--borda);
    background: var(--fundo); color: var(--texto); font-size: 14px; cursor: pointer;
  }
  button.principal { background: var(--marca); border-color: var(--marca); color: #fff; font-weight: 600; }
  button:disabled { opacity: .45; cursor: default; }
  #aviso { margin-right: auto; color: var(--alerta); font-size: 13px; }
  #aviso.ok { color: var(--marca); }
</style>
</head>
<body>
<header>
  <span class="id" id="id-cego">—</span>
  <span class="selo" id="selo-codificado" hidden>já codificado</span>
  <span class="meta" id="posicao">—</span>
  <span class="barra"><i id="progresso" style="width:0"></i></span>
  <span class="meta" id="rodada">—</span>
</header>
<main>
  <section><h2>item</h2><div class="corpo" id="ctx-item"></div></section>
  <section><h2>enunciado</h2><div class="corpo" id="ctx-enunciado"></div></section>
  <section><h2>código no prefixo</h2><pre class="corpo" id="ctx-codigo_no_prefixo"></pre></section>
  <section><h2>erros no prefixo</h2><pre class="corpo" id="ctx-erros_no_prefixo"></pre></section>
  <section><h2>conversa até aqui</h2><pre class="corpo" id="ctx-conversa_ate_aqui"></pre></section>
  <section><h2>turno do tutor</h2><pre class="corpo" id="ctx-turno_do_tutor"></pre></section>
  <section><h2>codificação</h2><form id="formulario"></form></section>
</main>
<footer>
  <span id="aviso"></span>
  <button type="button" id="anterior">← anterior</button>
  <button type="button" id="seguinte">seguinte →</button>
  <button type="button" class="principal" id="gravar">gravar e seguir</button>
</footer>
<script>
const DOMINIOS = __DOMINIOS__;
const CONTEXTO = __CONTEXTO__;
const LONGOS = __LONGOS__;
const LIVRE = __LIVRE__;

let estado = null;
let sujo = false;

const formulario = document.getElementById("formulario");
const aviso = document.getElementById("aviso");

for (const [campo, dominio] of Object.entries(DOMINIOS)) {
  const linha = document.createElement("div");
  linha.className = "campo";
  const rotulo = document.createElement("label");
  rotulo.textContent = campo.replace(/_/g, " ");
  const opcoes = document.createElement("div");
  opcoes.className = "opcoes";
  for (const valor of dominio) {
    const envolve = document.createElement("label");
    const entrada = document.createElement("input");
    entrada.type = "radio";
    entrada.name = campo;
    entrada.value = valor;
    entrada.addEventListener("change", () => { sujo = true; limparAviso(); });
    const texto = document.createElement("span");
    texto.textContent = valor;
    envolve.append(entrada, texto);
    opcoes.append(envolve);
  }
  linha.append(rotulo, opcoes);
  formulario.append(linha);
}
const linhaNotas = document.createElement("div");
linhaNotas.className = "campo";
const rotuloNotas = document.createElement("label");
rotuloNotas.textContent = LIVRE;
const notas = document.createElement("textarea");
notas.name = LIVRE;
notas.addEventListener("input", () => { sujo = true; });
linhaNotas.append(rotuloNotas, notas);
formulario.append(linhaNotas);

function limparAviso() { aviso.textContent = ""; aviso.className = ""; }

function desenhar(dados) {
  estado = dados;
  sujo = false;
  limparAviso();
  document.getElementById("id-cego").textContent = dados.registro.id_cego;
  document.getElementById("posicao").textContent =
    `${dados.indice + 1} de ${dados.total} · ${dados.codificados} codificados`;
  document.getElementById("rodada").textContent = `${dados.rodada} · ${dados.arquivo}`;
  document.getElementById("progresso").style.width =
    `${(dados.codificados / dados.total) * 100}%`;
  document.getElementById("selo-codificado").hidden = !dados.codificado;
  document.getElementById("ctx-item").textContent =
    `${dados.registro.item_id} · ${dados.registro.tipo_bug}`;
  document.getElementById("ctx-enunciado").textContent = dados.registro.enunciado;
  for (const campo of LONGOS) {
    document.getElementById(`ctx-${campo}`).textContent = dados.registro[campo];
  }
  for (const campo of Object.keys(DOMINIOS)) {
    const guardado = dados.codificacao[campo];
    for (const entrada of formulario.elements[campo]) {
      entrada.checked = entrada.value === guardado;
    }
  }
  notas.value = dados.codificacao[LIVRE] || "";
  document.getElementById("anterior").disabled = dados.indice === 0;
  document.getElementById("seguinte").disabled = dados.indice >= dados.total - 1;
  window.scrollTo(0, 0);
}

function recolher() {
  const valores = {};
  const faltam = [];
  for (const campo of Object.keys(DOMINIOS)) {
    const marcado = formulario.querySelector(`input[name="${campo}"]:checked`);
    if (!marcado || !DOMINIOS[campo].includes(marcado.value)) faltam.push(campo);
    else valores[campo] = marcado.value;
  }
  valores[LIVRE] = notas.value;
  return { valores, faltam };
}

async function ir(indice) {
  if (sujo && !confirm("Há alterações por gravar neste registro. Sair mesmo assim?")) return;
  const resposta = await fetch(`/api/estado?indice=${indice}`);
  desenhar(await resposta.json());
}

async function gravar() {
  const { valores, faltam } = recolher();
  if (faltam.length) {
    aviso.className = "";
    aviso.textContent = `por preencher: ${faltam.map(c => c.replace(/_/g, " ")).join(", ")}`;
    return;
  }
  const botao = document.getElementById("gravar");
  botao.disabled = true;
  try {
    const resposta = await fetch("/api/gravar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ indice: estado.indice, valores }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      aviso.className = "";
      aviso.textContent = (dados.erros || ["falha ao gravar"]).join(" · ");
      return;
    }
    const ultimo = estado.indice >= estado.total - 1;
    desenhar(dados);
    aviso.className = "ok";
    aviso.textContent = ultimo ? "gravado — rodada completa" : "gravado";
  } finally {
    botao.disabled = false;
  }
}

document.getElementById("gravar").addEventListener("click", gravar);
document.getElementById("anterior").addEventListener("click", () => ir(estado.indice - 1));
document.getElementById("seguinte").addEventListener("click", () => ir(estado.indice + 1));
document.addEventListener("keydown", (evento) => {
  if ((evento.metaKey || evento.ctrlKey) && evento.key === "Enter") { evento.preventDefault(); gravar(); }
});

fetch("/api/estado?indice=__INICIAL__").then(r => r.json()).then(desenhar);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(principal())
