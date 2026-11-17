"""Revisão local sem login: python -m revisor.cli RELATORIO --output PASTA."""
import argparse
from pathlib import Path
from .review import review_pdf
from .export import export_json, export_pdf


def main():
    parser = argparse.ArgumentParser(description="Revisão documental local; não autoriza emissão.")
    parser.add_argument("report")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--stage", choices=["rascunho", "antes_da_emissao"], default="antes_da_emissao")
    args = parser.parse_args()
    review = review_pdf(args.report, args.evidence, args.stage)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    export_json(review, root / "parecer.json")
    export_pdf(review, root / "parecer.pdf")
    print(f"{len(review.findings)} achados para revisão humana. Pareceres gravados em {root}.")


if __name__ == "__main__":
    main()
