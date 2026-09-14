"""Tarefa H.2 — o detector objetivo contra as alternativas de referência do banco.

O detector foi validado num sentido só (contra a codificação humana, em ``kappa``). O protocolo
pede o outro: **nenhum** turno de referência do banco — nem o texto adotado, nem as alternativas
anotadas — pode disparar o detector. Qualquer disparo é falso positivo e derruba a precisão de
1,000 reportada.

Dois testes, porque não são o mesmo:

``detector``
    ``avaliacao.detector.detectar`` exatamente como a bancada o usa: os padrões correm só sobre
    os **trechos de código** extraídos da mensagem e ignoram-se os já satisfeitos pelo código
    vigente do prefixo. É este que decide o nível 3 e, portanto, a precisão reportada.

``regex_cru``
    o padrão contra o **texto inteiro**, sem extração de trechos e sem o filtro do código
    vigente — o mesmo teste que ``avaliacao.itens._validar_fix_patterns`` faz em ``validar``.
    Mais severo: um disparo aqui sem disparo no detector é uma regex larga, não um falso
    positivo da medida.

Só leitura. Escreve em ``analise_tese/saida/``.

    python -m analise_tese.detector_referencias
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from avaliacao.config import BANCO_DIR  # noqa: E402
from avaliacao.detector import detectar  # noqa: E402
from avaliacao.itens import carregar_banco, expandir_prefixos  # noqa: E402
from analise_tese import comum  # noqa: E402


def main() -> None:
    itens = {item["id"]: item for item in carregar_banco(BANCO_DIR)}
    disparos_detector: list[dict] = []
    disparos_regex: list[dict] = []
    contagem = collections.Counter()

    for item_id, item in sorted(itens.items()):
        padroes = list(item.get("fix_patterns", []))
        compilados = [re.compile(p, re.IGNORECASE) for p in padroes]
        for prefixo in expandir_prefixos(item, com_pressao=False):
            textos = [("adotado", prefixo.referencia)]
            textos += [(f"alternativa_{i}", a) for i, a in enumerate(prefixo.alternativas, 1)]
            for papel, texto in textos:
                contagem["textos"] += 1
                contagem["adotados" if papel == "adotado" else "alternativas"] += 1
                veredito = detectar(texto, padroes, acoes=None, codigo_vigente=prefixo.code)
                if veredito.revelacao_codigo:
                    contagem["disparos_detector"] += 1
                    disparos_detector.append(
                        {
                            "prefixo_id": prefixo.id,
                            "item_id": item_id,
                            "k": prefixo.k,
                            "papel": papel,
                            "padroes": veredito.padroes,
                            "trechos": veredito.trechos,
                            "texto": texto,
                        }
                    )
                casados = [p.pattern for p in compilados if p.search(texto)]
                if casados:
                    contagem["disparos_regex_cru"] += 1
                    disparos_regex.append(
                        {
                            "prefixo_id": prefixo.id,
                            "item_id": item_id,
                            "k": prefixo.k,
                            "papel": papel,
                            "padroes": casados,
                            "texto": texto,
                        }
                    )

    relatorio = {
        "itens": len(itens),
        "prefixos_ouro": sum(
            1 for item in itens.values() for _ in expandir_prefixos(item, com_pressao=False)
        ),
        "textos_de_referencia_testados": contagem["textos"],
        "turnos_adotados": contagem["adotados"],
        "alternativas": contagem["alternativas"],
        "disparos_detector": contagem["disparos_detector"],
        "disparos_regex_cru": contagem["disparos_regex_cru"],
        "detalhe_detector": disparos_detector,
        "detalhe_regex_cru": disparos_regex,
    }
    destino = comum.escrever("detector_referencias.json", relatorio)
    resumo = {k: v for k, v in relatorio.items() if not k.startswith("detalhe_")}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(f"\n[escrito] {destino}", file=sys.stderr)


if __name__ == "__main__":
    main()
