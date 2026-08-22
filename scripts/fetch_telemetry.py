#!/usr/bin/env python3
"""
Baixa a telemetria do Blob Storage e consolida num NDJSON + CSV por evento.

Os lotes chegam como blobs independentes; retentativas do cliente podem
sobrepor faixas de ``seq``. A deduplicação por ``(sessionId, seq)`` acontece
aqui — é o passo que garante contagem de eventos correta na análise.

Uso:
    python scripts/fetch_telemetry.py --out dados/
    python scripts/fetch_telemetry.py --out dados/ --session sess-abc

A connection string vem de ``TELEMETRY_BLOB_CONNECTION_STRING`` (ou ``--connection-string``);
o contentor de ``TELEMETRY_BLOB_CONTAINER`` (default: ``telemetria``).
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_CONTAINER = "telemetria"

#: Colunas fixas do CSV; chaves extra dos eventos vão para a coluna ``extra`` (JSON).
BASE_COLUMNS = [
    "participantId",
    "condition",
    "installId",
    "sessionId",
    "seq",
    "ts",
    "serverTs",
    "type",
    "task",
    "errorClass",
    "tabKey",
    "buildSha",
    "promptHash",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Pasta de saída.")
    parser.add_argument(
        "--connection-string",
        default=os.getenv("TELEMETRY_BLOB_CONNECTION_STRING", ""),
        help="Connection string da conta de armazenamento.",
    )
    parser.add_argument(
        "--container",
        default=os.getenv("TELEMETRY_BLOB_CONTAINER") or DEFAULT_CONTAINER,
        help=f"Contentor (default: {DEFAULT_CONTAINER}).",
    )
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="Filtra por sessionId (repetível). Sem filtro, baixa tudo.",
    )
    return parser.parse_args()


def iter_event_lines(container: Any, session_filter: set[str]) -> Any:
    for blob in container.list_blobs(name_starts_with="sessions/"):
        # sessions/{installId}/{sessionId}/{faixa}.ndjson
        parts = blob.name.split("/")
        if session_filter and (len(parts) < 3 or parts[2] not in session_filter):
            continue
        raw = container.get_blob_client(blob.name).download_blob().readall()
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                yield blob.name, line


def main() -> int:
    args = parse_args()
    if not args.connection_string.strip():
        print(
            "Defina TELEMETRY_BLOB_CONNECTION_STRING ou use --connection-string.",
            file=sys.stderr,
        )
        return 2

    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(args.connection_string)
    container = service.get_container_client(args.container)

    events: dict[tuple[str, int], dict[str, Any]] = {}
    duplicates = 0
    malformed = 0
    blobs_read: set[str] = set()

    for blob_name, line in iter_event_lines(container, set(args.session)):
        blobs_read.add(blob_name)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        key = (str(event.get("sessionId")), int(event.get("seq", -1)))
        if key in events:
            duplicates += 1
            continue
        events[key] = event

    ordered = sorted(events.values(), key=lambda e: (str(e.get("sessionId")), e.get("seq", 0)))

    args.out.mkdir(parents=True, exist_ok=True)
    ndjson_path = args.out / "events.ndjson"
    csv_path = args.out / "events.csv"

    with ndjson_path.open("w", encoding="utf-8") as handle:
        for event in ordered:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*BASE_COLUMNS, "extra"])
        writer.writeheader()
        for event in ordered:
            row = {column: event.get(column) for column in BASE_COLUMNS}
            extra = {k: v for k, v in event.items() if k not in BASE_COLUMNS}
            row["extra"] = json.dumps(extra, ensure_ascii=False) if extra else ""
            writer.writerow(row)

    sessions = Counter(str(event.get("sessionId")) for event in ordered)
    participants = Counter(str(event.get("participantId")) for event in ordered)

    print(f"blobs lidos        : {len(blobs_read)}")
    print(f"eventos únicos     : {len(ordered)}")
    print(f"duplicados (retry) : {duplicates}")
    print(f"linhas inválidas   : {malformed}")
    print(f"sessões            : {len(sessions)}")
    print(f"participantes      : {sorted(participants)}")
    print(f"\n{ndjson_path}\n{csv_path}")

    # Lacuna de seq indica evento perdido — a tese prevê análise de sensibilidade.
    for session_id in sessions:
        seqs = sorted(
            event["seq"] for event in ordered if str(event.get("sessionId")) == session_id
        )
        gaps = [
            (a, b) for a, b in zip(seqs, seqs[1:], strict=False) if b - a > 1
        ]
        if gaps:
            print(f"\nAVISO {session_id}: lacunas de seq {gaps}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
