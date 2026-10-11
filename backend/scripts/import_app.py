from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def validate_metadata(metadata: Any) -> list[str]:
    errors = []
    if not isinstance(metadata, dict):
        return ["Root of metadata must be a JSON object."]

    app = metadata.get("app")
    if not isinstance(app, dict):
        errors.append("Metadata must have an 'app' object.")
    else:
        if not app.get("id"):
            errors.append("app.id is required.")
        if not app.get("name"):
            errors.append("app.name is required.")

    pages = metadata.get("pages")
    if not isinstance(pages, list) or len(pages) == 0:
        errors.append("Metadata must have a non-empty 'pages' array.")
    else:
        for idx, p in enumerate(pages):
            if not isinstance(p, dict):
                errors.append(f"Page at index {idx} must be an object.")
                continue
            if not p.get("id"):
                errors.append(f"Page at index {idx} is missing 'id'.")
            if not p.get("title"):
                errors.append(f"Page '{p.get('id', idx)}' is missing 'title'.")
            if not p.get("route"):
                errors.append(f"Page '{p.get('id', idx)}' is missing 'route'.")
            widgets = p.get("widgets")
            if widgets is not None and isinstance(widgets, list):
                for w_idx, w in enumerate(widgets):
                    if not isinstance(w, dict):
                        errors.append(f"Widget {w_idx} on page '{p.get('id')}' must be an object.")
                    elif not w.get("id") or not w.get("type"):
                        errors.append(f"Widget {w_idx} on page '{p.get('id')}' is missing 'id' or 'type'.")

    directories = metadata.get("directories")
    if not isinstance(directories, list) or len(directories) == 0:
        errors.append("Metadata must have a non-empty 'directories' array.")
    else:
        for idx, d in enumerate(directories):
            if not isinstance(d, dict) or not d.get("id") or not d.get("title"):
                errors.append(f"Directory at index {idx} must have 'id' and 'title'.")

    if "dimensions" not in metadata or not isinstance(metadata.get("dimensions"), dict):
        errors.append("Metadata must have a 'dimensions' object.")

    return errors


def import_app(file_path: Path | str) -> bool:
    path = Path(file_path).resolve()
    if not path.is_file():
        print(f"Error: File not found: {path}", file=sys.stderr)
        return False

    try:
        content = path.read_text(encoding="utf-8")
        metadata = json.loads(content)
    except Exception as exc:
        print(f"Error reading JSON from {path}: {exc}", file=sys.stderr)
        return False

    errors = validate_metadata(metadata)
    if errors:
        print(f"Validation failed for {path}:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return False

    app_id = metadata["app"]["id"]
    target_dir = ROOT / "data" / "apps" / app_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_meta_path = target_dir / "app_metadata.json"
    target_meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build retrieval index
    try:
        from app.retrieval import build_index
        build_index(metadata)
    except Exception as exc:
        print(f"Warning: Failed to build retrieval index: {exc}", file=sys.stderr)

    print(f"Successfully imported app '{metadata['app']['name']}' ({app_id}) to {target_dir}")
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python import_app.py <path/to/metadata.json>", file=sys.stderr)
        sys.exit(1)

    success = import_app(sys.argv[1])
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
