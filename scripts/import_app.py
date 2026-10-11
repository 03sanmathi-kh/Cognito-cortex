from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SCRIPT = ROOT / "backend" / "scripts" / "import_app.py"

if __name__ == "__main__":
    if str(ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(ROOT / "backend"))
    import runpy
    runpy.run_path(str(BACKEND_SCRIPT), run_name="__main__")
