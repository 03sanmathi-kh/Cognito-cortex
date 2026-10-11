import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

MODEL_NAME = "all-MiniLM-L6-v2"
CACHE_ROOT = Path(__file__).resolve().parents[2] / ".cache"
_RRF_CONSTANT = 60
_LOCK = threading.RLock()
_DOCUMENTS: list[dict[str, Any]] = []
_INDEX: faiss.Index | None = None
_BM25: BM25Okapi | None = None
_MODEL: Any = None
_INDEX_HASH: str | None = None
_ROLE_LOOKUP: dict[str, str] = {}


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _normalise_role(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def get_roles(metadata: dict[str, Any]) -> list[dict[str, str]]:
    """Return a metadata-defined role catalog or derive one from page access lists."""
    catalog = metadata.get("roles")
    if catalog is None:
        catalog = (metadata.get("app") or {}).get("roles")

    role_entries: dict[str, str] = {}
    if isinstance(catalog, list):
        for role in catalog:
            if isinstance(role, str):
                role_id = role
                display_name = re.sub(r"[_-]+", " ", role).strip().title()
            elif isinstance(role, dict):
                role_id = role.get("id") or role.get("role_id")
                display_name = role.get("display_name") or role.get("name") or role.get("label")
                if role_id is None:
                    continue
                display_name = display_name or re.sub(r"[_-]+", " ", str(role_id)).strip().title()
            else:
                continue
            role_entries[str(role_id)] = str(display_name)

    for page in metadata.get("pages") or []:
        allowed_roles = page.get("allowed_roles") or []
        if isinstance(allowed_roles, str):
            allowed_roles = [allowed_roles]
        for role in allowed_roles:
            if isinstance(role, dict):
                role_id = role.get("id") or role.get("role_id")
                display_name = role.get("display_name") or role.get("name") or role.get("label")
                if role_id is None:
                    continue
                role = role_id
                if display_name:
                    role_entries.setdefault(str(role_id), str(display_name))
            role_id = str(role)
            role_entries.setdefault(role_id, re.sub(r"[_-]+", " ", role_id).strip().title())

    return [{"id": role_id, "display_name": display_name} for role_id, display_name in role_entries.items()]


def _directory_maps(metadata: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    directories: dict[str, str] = {}
    subdirectories: dict[str, dict[str, str]] = {}
    for directory in metadata.get("directories") or []:
        directory_id = directory.get("id")
        if directory_id is None:
            continue
        directories[directory_id] = directory.get("title", str(directory_id))
        subdirectories[directory_id] = {
            item.get("id"): item.get("title", str(item.get("id")))
            for item in directory.get("subdirectories", [])
            if item.get("id") is not None
        }
    return directories, subdirectories


def _option_text(options: list[Any]) -> str:
    labels = []
    for option in options:
        if isinstance(option, dict):
            labels.append(str(option.get("label") or option.get("title") or option.get("field") or option.get("id") or ""))
        else:
            labels.append(str(option))
    return " ".join(labels)


def _build_documents(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    directory_titles, subdirectory_titles = _directory_maps(metadata)
    documents: list[dict[str, Any]] = []

    for page in metadata.get("pages") or []:
        page_id = page.get("id")
        if page_id is None:
            continue

        directory_id = page.get("directory")
        subdirectory_id = page.get("subdirectory")
        breadcrumb_parts = [
            directory_titles.get(directory_id, str(directory_id)) if directory_id else None,
            subdirectory_titles.get(directory_id, {}).get(subdirectory_id, str(subdirectory_id)) if subdirectory_id else None,
            page.get("title"),
        ]
        breadcrumb = " / ".join(str(part) for part in breadcrumb_parts if part)
        filters = page.get("filters") or []
        filter_names = [str(item.get("name", "")) for item in filters if item.get("name")]
        sort_text = _option_text(page.get("sort_options") or [])
        date_text = _option_text(page.get("date_range_options") or [])
        page_widgets = page.get("widgets") or []
        keyword_text = " ".join(str(keyword) for keyword in (page.get("keywords") or []))
        widget_context = " ".join(
            f"{item.get('title', '')} {item.get('type', '')}"
            for item in page_widgets
        )
        common_text = " ".join(str(part) for part in [
            breadcrumb,
            page.get("title", ""),
            page.get("description", ""),
            keyword_text,
            widget_context,
            " ".join(filter_names),
            sort_text,
            date_text,
        ] if part is not None and str(part).strip())
        allowed_roles = page.get("allowed_roles")
        if isinstance(allowed_roles, str):
            allowed_roles = [allowed_roles]
        access = {
            "allowed_roles": allowed_roles,
            "region_scoped": page.get("region_scoped"),
        }
        documents.append({
            "id": str(page_id),
            "type": "page",
            "page_id": str(page_id),
            "widget_id": None,
            "title": str(page.get("title") or page_id),
            "breadcrumb": breadcrumb,
            "allowed_roles": access["allowed_roles"],
            "region_scoped": access["region_scoped"],
            "text": common_text,
        })

        for widget in page_widgets:
            widget_id = widget.get("id")
            if widget_id is None:
                continue
            widget_title = str(widget.get("title") or widget_id)
            widget_type = str(widget.get("type") or "")
            documents.append({
                "id": str(widget_id),
                "type": "widget",
                "page_id": str(page_id),
                "widget_id": str(widget_id),
                "title": widget_title,
                "breadcrumb": breadcrumb,
                "allowed_roles": access["allowed_roles"],
                "region_scoped": access["region_scoped"],
                "text": " ".join(str(part) for part in [
                    breadcrumb,
                    page.get("title", ""),
                    page.get("description", ""),
                    widget_title,
                    widget_type,
                    keyword_text,
                    " ".join(filter_names),
                    sort_text,
                    date_text,
                ] if part is not None and str(part).strip()),
            })

    return documents


def _metadata_hash(metadata: dict[str, Any]) -> str:
    canonical = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_model():
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from sentence_transformers import SentenceTransformer

            _MODEL = SentenceTransformer(MODEL_NAME)
        return _MODEL


def build_index(metadata: dict[str, Any]) -> None:
    """Load or build the semantic and lexical indexes for application metadata."""
    global _DOCUMENTS, _INDEX, _BM25, _INDEX_HASH, _ROLE_LOOKUP

    metadata_hash = _metadata_hash(metadata)
    role_lookup: dict[str, str] = {}
    for role in get_roles(metadata):
        canonical_id = role["id"]
        role_lookup[_normalise_role(canonical_id)] = canonical_id
        role_lookup[_normalise_role(role["display_name"])] = canonical_id

    with _LOCK:
        if _INDEX_HASH == metadata_hash and _INDEX is not None and _BM25 is not None:
            return

        cache_dir = CACHE_ROOT / metadata_hash
        index_path = cache_dir / "vectors.faiss"
        documents_path = cache_dir / "documents.json"
        if index_path.is_file() and documents_path.is_file():
            documents = json.loads(documents_path.read_text(encoding="utf-8"))
            vector_index = faiss.read_index(str(index_path))
        else:
            documents = _build_documents(metadata)
            if not documents:
                raise ValueError("App metadata contains no searchable pages or widgets")
            embeddings = _get_model().encode(
                [document["text"] for document in documents],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            embeddings = np.asarray(embeddings, dtype=np.float32)
            vector_index = faiss.IndexFlatIP(embeddings.shape[1])
            vector_index.add(embeddings)
            cache_dir.mkdir(parents=True, exist_ok=True)
            faiss.write_index(vector_index, str(index_path))
            documents_path.write_text(json.dumps(documents, ensure_ascii=False), encoding="utf-8")

        tokenized = [_tokens(document["text"]) for document in documents]
        _DOCUMENTS = documents
        _INDEX = vector_index
        _BM25 = BM25Okapi(tokenized)
        _INDEX_HASH = metadata_hash
        _ROLE_LOOKUP = role_lookup


def search(query: str, k: int = 5, role: str | None = None) -> list[dict[str, Any]]:
    """Return hybrid semantic and BM25 results combined with reciprocal rank fusion."""
    if k <= 0:
        return []

    with _LOCK:
        if _INDEX is None or _BM25 is None or not _DOCUMENTS:
            raise RuntimeError("Retrieval index has not been built")
        documents = _DOCUMENTS
        vector_index = _INDEX
        bm25 = _BM25
        role_lookup = _ROLE_LOOKUP

    if role:
        canonical_role = role_lookup.get(_normalise_role(role))
        if canonical_role is None:
            available_roles = ", ".join(dict.fromkeys(role_lookup.values()))
            raise ValueError(f"Unknown role '{role}'. Available role IDs: {available_roles or 'none'}")
        role = canonical_role

    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    query_embedding = _get_model().encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    semantic_count = len(documents)
    _, semantic_indices = vector_index.search(np.asarray(query_embedding, dtype=np.float32), semantic_count)
    semantic_ranked = [int(index) for index in semantic_indices[0] if index >= 0]

    lexical_scores = bm25.get_scores(query_tokens)
    lexical_order = np.argsort(lexical_scores)[::-1]
    lexical_ranked = [int(index) for index in lexical_order if lexical_scores[index] > 0]

    fused_scores: dict[int, float] = {}
    for ranked_list in (semantic_ranked, lexical_ranked):
        for rank, document_index in enumerate(ranked_list, start=1):
            fused_scores[document_index] = fused_scores.get(document_index, 0.0) + 1.0 / (_RRF_CONSTANT + rank)

    results = []
    accessible_roles = {_normalise_role(role)} if role else set()
    if _normalise_role(role or "") == "regionalmanager":
        accessible_roles.add(_normalise_role("analyst"))
    for document_index, score in sorted(fused_scores.items(), key=lambda item: item[1], reverse=True):
        document = documents[document_index]
        allowed_roles = document.get("allowed_roles")
        if role and allowed_roles and not any(_normalise_role(str(allowed_role)) in accessible_roles for allowed_role in allowed_roles):
            continue
        results.append({
            "id": document["id"],
            "type": document["type"],
            "page_id": document["page_id"],
            "widget_id": document.get("widget_id"),
            "title": document["title"],
            "breadcrumb": document["breadcrumb"],
            "score": float(score),
        })
        if len(results) >= k:
            break

    try:
        from app.graph import enrich_search_results

        results = enrich_search_results(results)
    except ImportError:
        pass
    return results
