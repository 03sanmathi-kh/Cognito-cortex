from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

STEPS = [
    ("generate data", BACKEND_ROOT / "scripts" / "generate_data.py"),
    ("create views", BACKEND_ROOT / "scripts" / "create_views.py"),
    ("validate views", BACKEND_ROOT / "scripts" / "validate_views.py"),
    ("verify data", BACKEND_ROOT / "scripts" / "verify_data.py"),
    ("enrich metadata", ROOT / "data" / "scripts" / "enrich_metadata.py"),
    ("check metadata", ROOT / "data" / "scripts" / "check_metadata.py"),
]


def main() -> None:
    for step_name, script in STEPS:
        print(f"Running {step_name}...", flush=True)
        result = subprocess.run([sys.executable, str(script)], cwd=BACKEND_ROOT, check=False)
        if result.returncode != 0:
            raise SystemExit(
                f"Data setup failed during {step_name} (exit code {result.returncode}). "
                "If business.duckdb is locked, close the backend server and rerun."
            )

    print("Building retrieval index...", flush=True)
    metadata_path = ROOT / "data" / "app_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    from app.retrieval import build_index

    build_index(metadata)
    print("Data setup complete.", flush=True)


if __name__ == "__main__":
    main()
