from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APPS_DIR = ROOT / "data" / "apps"

_ACTIVE_APP_ID: str = "meridian"


def get_active_app_id() -> str:
    return _ACTIVE_APP_ID


def get_app(app_id: str) -> dict[str, Any] | None:
    for app in list_apps():
        if app["id"] == app_id:
            return app
    return None


def list_apps() -> list[dict[str, Any]]:
    apps = [
        {
            "id": "meridian",
            "name": "Meridian Distribution",
            "description": "Multi-region distribution company (sales, orders, inventory, finance)",
            "active": _ACTIVE_APP_ID == "meridian",
        }
    ]

    if APPS_DIR.exists():
        for child in APPS_DIR.iterdir():
            if child.is_dir():
                app_meta_path = child / "app_metadata.json"
                if app_meta_path.exists():
                    try:
                        meta = json.loads(app_meta_path.read_text(encoding="utf-8"))
                        app_info = meta.get("app") or {}
                        app_id = app_info.get("id") or child.name
                        if app_id != "meridian":
                            apps.append({
                                "id": app_id,
                                "name": app_info.get("name", child.name.title()),
                                "description": app_info.get("description", f"{app_id} application"),
                                "active": _ACTIVE_APP_ID == app_id,
                            })
                    except Exception:
                        pass
    return apps


def get_active_metadata_path() -> Path:
    if _ACTIVE_APP_ID == "meridian":
        return ROOT / "data" / "app_metadata.json"
    custom_path = APPS_DIR / _ACTIVE_APP_ID / "app_metadata.json"
    if custom_path.exists():
        return custom_path
    return ROOT / "data" / "app_metadata.json"


def get_active_metadata() -> dict[str, Any]:
    path = get_active_metadata_path()
    return json.loads(path.read_text(encoding="utf-8"))


def get_active_db_path() -> Path:
    if _ACTIVE_APP_ID == "meridian":
        return ROOT / "data" / "business.duckdb"
    for candidate in [
        APPS_DIR / _ACTIVE_APP_ID / f"{_ACTIVE_APP_ID}.duckdb",
        APPS_DIR / _ACTIVE_APP_ID / "clinic.duckdb",
        APPS_DIR / _ACTIVE_APP_ID / "business.duckdb",
    ]:
        if candidate.exists():
            return candidate
    return ROOT / "data" / "business.duckdb"


def get_active_catalog_path() -> Path:
    if _ACTIVE_APP_ID == "meridian":
        return ROOT / "data" / "analysis_catalog.json"
    custom_path = APPS_DIR / _ACTIVE_APP_ID / "analysis_catalog.json"
    if custom_path.exists():
        return custom_path
    return ROOT / "data" / "analysis_catalog.json"


def get_active_views_path() -> Path:
    if _ACTIVE_APP_ID == "meridian":
        return ROOT / "data" / "views_manifest.json"
    custom_path = APPS_DIR / _ACTIVE_APP_ID / "views_manifest.json"
    if custom_path.exists():
        return custom_path
    return ROOT / "data" / "views_manifest.json"


def select_app(app_id: str) -> dict[str, Any]:
    global _ACTIVE_APP_ID
    app = get_app(app_id)
    if not app:
        raise ValueError(f"Unknown application '{app_id}'")
    _ACTIVE_APP_ID = app_id

    # Invalidate graph cache
    try:
        from app import graph
        graph._GRAPH = None
        graph._SOURCE_HASH = None
        graph._METADATA = {}
        graph.get_graph()
    except Exception:
        pass

    # Build retrieval index for the newly active app
    try:
        from app import retrieval
        retrieval._INDEX = None
        retrieval._BM25 = None
        retrieval._DOCUMENTS = []
        retrieval._INDEX_HASH = None
        retrieval.build_index(get_active_metadata())
    except Exception:
        pass

    # Reset analysis catalog and engine
    try:
        from app.analysis import catalog as analysis_catalog, engine as analysis_engine
        analysis_catalog._CACHED_CATALOG = None
        analysis_engine._ENGINE = None
        cpath = get_active_catalog_path()
        dpath = get_active_db_path()
        if cpath.exists() and dpath.exists():
            analysis_catalog.load_catalog(cpath, dpath, validate=False)
    except Exception:
        pass

    return {
        "ok": True,
        "active_app_id": _ACTIVE_APP_ID,
        "app": app,
    }
