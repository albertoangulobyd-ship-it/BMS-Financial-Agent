"""Interfaz de linea de comandos de la fase 0.

Tres ordenes, ninguna escribe en ningun sistema de la empresa:

    bms-agent schema              muestra el esquema de extraccion
    bms-agent extract facturas/   extrae los PDF de una carpeta a out/
    bms-agent score               compara out/ con las respuestas a mano
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .documents import UnsupportedDocument, iter_pdfs, load_pdf
from .extract import extract_invoice
from .schema import InvoiceExtraction
from .scoring import Report, load_ground_truth, score_document, format_report


def _cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(InvoiceExtraction.model_json_schema(), indent=2, ensure_ascii=False))
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    try:
        import anthropic
    except ImportError:
        print("Falta el paquete anthropic. Instala con: pip install -e .", file=sys.stderr)
        return 2

    pdfs = list(iter_pdfs(args.directory))
    if not pdfs:
        print(f"No hay PDF en {args.directory}", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()
    out_dir = Path(args.out)
    model = config.model_id()
    print(f"Extrayendo {len(pdfs)} documentos con {model}\n")

    failures = 0
    for path in pdfs:
        try:
            doc = load_pdf(path)
        except UnsupportedDocument as exc:
            print(f"  omitido  {path.name}: {exc}")
            failures += 1
            continue

        try:
            record = extract_invoice(client, doc, model=model)
        except Exception as exc:  # la fase 0 no se detiene por un documento
            print(f"  ERROR    {path.name}: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        target = record.write_json(out_dir)
        flagged = record.extraction.low_confidence_fields
        suffix = f"  (dudoso: {', '.join(flagged)})" if flagged else ""
        print(f"  ok       {path.name} -> {target.name}{suffix}")

    print(f"\nHecho. {len(pdfs) - failures} de {len(pdfs)} extraidos en {out_dir}/")
    return 1 if failures else 0


def _cmd_score(args: argparse.Namespace) -> int:
    truth = load_ground_truth(args.ground_truth)
    if not truth:
        print(f"{args.ground_truth} esta vacio", file=sys.stderr)
        return 1

    by_name = {}
    for json_path in sorted(Path(args.out).glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        by_name[payload["source_name"]] = payload

    scores = []
    missing = []
    for source_name, expected in truth.items():
        payload = by_name.get(source_name)
        if payload is None:
            missing.append(source_name)
            continue
        scores.append(score_document(source_name, payload["extraction"], expected))

    if missing:
        print(f"Sin extraccion para {len(missing)} documentos: {', '.join(missing)}\n")

    if not scores:
        print("No hay nada que puntuar.", file=sys.stderr)
        return 1

    print(format_report(Report(documents=scores)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bms-agent", description="Fase 0: observador. No escribe en ningun sistema."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_schema = sub.add_parser("schema", help="muestra el esquema de extraccion")
    p_schema.set_defaults(func=_cmd_schema)

    p_extract = sub.add_parser("extract", help="extrae los PDF de una carpeta")
    p_extract.add_argument("directory", help="carpeta con los PDF")
    p_extract.add_argument("--out", default="out", help="carpeta de salida (por defecto: out)")
    p_extract.set_defaults(func=_cmd_extract)

    p_score = sub.add_parser("score", help="compara las extracciones con las respuestas")
    p_score.add_argument("--out", default="out", help="carpeta con las extracciones")
    p_score.add_argument(
        "--ground-truth",
        default="ground_truth/respuestas.yaml",
        help="fichero de respuestas escritas a mano",
    )
    p_score.set_defaults(func=_cmd_score)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
