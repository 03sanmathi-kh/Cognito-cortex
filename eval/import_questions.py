from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.languages import detect_language
except ImportError:
    def detect_language(text: str) -> str:
        return "en"


def load_metadata_pages(app: str) -> dict[str, dict[str, Any]]:
    if app == "clinic":
        meta_path = ROOT / "data" / "apps" / "clinic" / "app_metadata.json"
    else:
        meta_path = ROOT / "data" / "app_metadata.json"

    if not meta_path.exists():
        return {}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    pages_by_id_or_title: dict[str, dict[str, Any]] = {}
    for p in meta.get("pages", []):
        pid = p["id"]
        title = p.get("title", pid)
        pages_by_id_or_title[pid.lower()] = p
        pages_by_id_or_title[title.lower()] = p
    return pages_by_id_or_title


def import_csv(
    csv_path: Path,
    output_path: Path,
    app: str = "sales",
) -> list[dict[str, Any]]:
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return []

    pages_lookup = load_metadata_pages(app)
    imported: list[dict[str, Any]] = []
    unknown_pages: list[tuple[int, str]] = []

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            row_id = row.get("id") or f"imported-{idx:03d}"
            message = row.get("message") or row.get("question") or ""
            if not message:
                continue

            raw_page = (row.get("page_id") or row.get("page") or "").strip()
            canonical_page_id = None
            if raw_page:
                match = pages_lookup.get(raw_page.lower())
                if match:
                    canonical_page_id = match["id"]
                else:
                    unknown_pages.append((idx, raw_page))
                    print(f"Warning [Row {idx} / ID {row_id}]: Unknown page '{raw_page}' not in metadata. Skipping.", file=sys.stderr)
                    continue

            raw_filters = row.get("filters")
            filters: dict[str, Any] = {}
            if raw_filters:
                try:
                    filters = json.loads(raw_filters) if raw_filters.startswith("{") else {}
                except Exception:
                    filters = {}

            lang = row.get("language") or detect_language(message)
            group = row.get("group") or ("navigation" if canonical_page_id else "analysis")
            role = row.get("role") or "analyst"
            split = row.get("split") or "dev"
            outcome = row.get("outcome") or "answered"

            raw_prev = row.get("previous")
            prev_messages = None
            if raw_prev:
                try:
                    prev_messages = json.loads(raw_prev) if raw_prev.startswith("[") else [raw_prev]
                except Exception:
                    prev_messages = [raw_prev]

            item = {
                "id": row_id,
                "app": app,
                "language": lang,
                "group": group,
                "message": message,
                "previous": prev_messages,
                "role": role,
                "split": split,
                "expected": {
                    "outcome": outcome,
                    "page_id": canonical_page_id,
                    "filters": filters,
                    "date_range": row.get("date_range") or None,
                    "sort": row.get("sort") or None,
                    "metric": row.get("metric") or None,
                    "dimension": row.get("dimension") or None,
                    "must_not": row.get("must_not") or None,
                },
            }
            imported.append(item)

    if unknown_pages:
        print(f"\nTotal unknown pages reported: {len(unknown_pages)} (these rows were excluded).", file=sys.stderr)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(imported, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Imported {len(imported)} valid items to {output_path}")
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import questions from CSV into testset JSON format.")
    parser.add_argument("--csv", type=Path, default=ROOT / "eval" / "friend_questions.csv", help="Path to CSV file")
    parser.add_argument("--output", type=Path, default=ROOT / "eval" / "imported_questions.json", help="Path to output JSON")
    parser.add_argument("--app", choices=["sales", "clinic"], default="sales", help="Application target")

    args = parser.parse_args()
    import_csv(args.csv, args.output, args.app)


if __name__ == "__main__":
    main()
