import difflib
import hashlib
import json
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx

METADATA_PATH = Path(__file__).resolve().parents[2] / "data" / "app_metadata.json"
_LOCK = threading.RLock()
_GRAPH: nx.DiGraph | None = None
_METADATA: dict[str, Any] = {}
_SOURCE_HASH: str | None = None


def _normalise(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _role_id(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _page_key(page_id: str) -> str:
    return f"page:{page_id}"


def _directory_maps(metadata: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    directories: dict[str, dict[str, Any]] = {}
    subdirectories: dict[str, dict[str, dict[str, Any]]] = {}
    for directory in metadata.get("directories") or []:
        directory_id = str(directory.get("id", ""))
        if not directory_id:
            continue
        directories[directory_id] = directory
        subdirectories[directory_id] = {
            str(item.get("id")): item
            for item in (directory.get("subdirectories") or [])
            if item.get("id") is not None
        }
    return directories, subdirectories


def _page_similarity_text(page: dict[str, Any]) -> set[str]:
    source = " ".join([
        str(page.get("title", "")),
        " ".join(str(keyword) for keyword in (page.get("keywords") or [])),
    ])
    return set(_normalise(source).split())


def _build_graph(metadata: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    app = metadata.get("app") or {}
    app_id = str(app.get("id", "app"))
    app_node = f"app:{app_id}"
    graph.add_node(app_node, **{**app, "type": "app"})

    directories, subdirectories = _directory_maps(metadata)
    for directory_id, directory in directories.items():
        directory_node = f"directory:{directory_id}"
        graph.add_node(directory_node, **{**directory, "type": "directory"})
        graph.add_edge(app_node, directory_node, type="contains")

        for subdirectory_id, subdirectory in subdirectories.get(directory_id, {}).items():
            subdirectory_node = f"subdirectory:{directory_id}:{subdirectory_id}"
            graph.add_node(
                subdirectory_node,
                **{**subdirectory, "type": "subdirectory", "directory_id": directory_id},
            )
            graph.add_edge(directory_node, subdirectory_node, type="contains")

    pages = metadata.get("pages") or []
    page_nodes: dict[str, str] = {}
    for page in pages:
        page_id = str(page.get("id", ""))
        if not page_id:
            continue
        page_node = _page_key(page_id)
        page_nodes[page_id] = page_node
        page_data = {**page, "type": "page"}
        graph.add_node(page_node, **page_data)

        directory_id = str(page.get("directory", ""))
        subdirectory_id = str(page.get("subdirectory", ""))
        if subdirectory_id and subdirectory_id in subdirectories.get(directory_id, {}):
            parent_node = f"subdirectory:{directory_id}:{subdirectory_id}"
        else:
            parent_node = f"directory:{directory_id}"
        if parent_node in graph:
            graph.add_edge(parent_node, page_node, type="contains")

        for widget in page.get("widgets") or []:
            widget_id = str(widget.get("id", ""))
            if not widget_id:
                continue
            widget_node = f"widget:{page_id}:{widget_id}"
            graph.add_node(widget_node, **{**widget, "type": "widget", "page_id": page_id})
            graph.add_edge(page_node, widget_node, type="has_widget")

        for filter_data in page.get("filters") or []:
            filter_name = str(filter_data.get("name", ""))
            if not filter_name:
                continue
            filter_node = f"filter:{page_id}:{filter_name}"
            graph.add_node(filter_node, **{**filter_data, "type": "filter", "page_id": page_id})
            graph.add_edge(page_node, filter_node, type="has_filter")

    page_tokens = {
        str(page.get("id")): _page_similarity_text(page)
        for page in pages
        if page.get("id") is not None
    }
    for page_id, tokens in page_tokens.items():
        comparisons = []
        for other_id, other_tokens in page_tokens.items():
            if page_id == other_id or not tokens or not other_tokens:
                continue
            overlap = len(tokens & other_tokens)
            if not overlap:
                continue
            score = overlap / (len(tokens | other_tokens))
            comparisons.append((score, other_id))
        for score, other_id in sorted(comparisons, reverse=True)[:3]:
            graph.add_edge(page_nodes[page_id], page_nodes[other_id], type="similar_to", score=float(score))

    return graph


def get_graph() -> nx.DiGraph:
    """Return the process-wide graph, rebuilding it only when metadata bytes change."""
    global _GRAPH, _METADATA, _SOURCE_HASH
    try:
        from app.apps import get_active_metadata_path
        meta_path = get_active_metadata_path()
    except Exception:
        meta_path = METADATA_PATH
    metadata_bytes = meta_path.read_bytes()
    source_hash = hashlib.sha256(metadata_bytes).hexdigest()
    with _LOCK:
        if _GRAPH is not None and _SOURCE_HASH == source_hash:
            return _GRAPH
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        graph = _build_graph(metadata)
        _GRAPH = graph
        _METADATA = metadata
        _SOURCE_HASH = source_hash
        return graph


def _metadata() -> dict[str, Any]:
    get_graph()
    return _METADATA


def _page_data(page_id: str) -> dict[str, Any] | None:
    graph = get_graph()
    node = _page_key(page_id)
    if node not in graph or graph.nodes[node].get("type") != "page":
        return None
    return dict(graph.nodes[node])


def _option_id(option: Any) -> str | None:
    if isinstance(option, dict):
        value = option.get("id") or option.get("field") or option.get("value")
        return None if value is None else str(value)
    return None if option is None else str(option)


def _option_label(option: Any) -> str:
    if isinstance(option, dict):
        return str(option.get("label") or option.get("title") or option.get("display_name") or _option_id(option) or "")
    return str(option)


def _similar_pages(page_id: str) -> list[dict[str, Any]]:
    graph = get_graph()
    node = _page_key(page_id)
    if node not in graph:
        return []
    similar = [
        {"id": target.removeprefix("page:"), "title": graph.nodes[target].get("title", ""), "score": data.get("score", 0.0)}
        for _, target, data in graph.out_edges(node, data=True)
        if data.get("type") == "similar_to"
    ]
    return sorted(similar, key=lambda item: item["score"], reverse=True)


def get_page(page_id: str) -> dict[str, Any] | None:
    return _page_data(page_id)


def get_breadcrumb(page_id: str) -> list[str]:
    page = _page_data(page_id)
    if page is None:
        return []
    graph = get_graph()
    node = _page_key(page_id)
    parent = next((source for source, _, data in graph.in_edges(node, data=True) if data.get("type") == "contains"), None)
    labels = []
    if parent and graph.nodes[parent].get("type") == "subdirectory":
        labels.append(str(graph.nodes[parent].get("title", "")))
        parent = next((source for source, _, data in graph.in_edges(parent, data=True) if data.get("type") == "contains"), None)
    if parent and graph.nodes[parent].get("type") == "directory":
        labels.append(str(graph.nodes[parent].get("title", "")))
    if page.get("title"):
        labels.append(str(page["title"]))
    return list(reversed([label for label in labels if label]))


def get_page_neighborhood(page_id: str) -> dict[str, Any] | None:
    page = _page_data(page_id)
    if page is None:
        return None
    graph = get_graph()
    node = _page_key(page_id)
    contains_parent = next((source for source, _, data in graph.in_edges(node, data=True) if data.get("type") == "contains"), None)
    directory_node = None
    if contains_parent:
        if graph.nodes[contains_parent].get("type") == "subdirectory":
            directory_node = next((source for source, _, data in graph.in_edges(contains_parent, data=True) if data.get("type") == "contains"), None)
            sibling_parent = contains_parent
        else:
            directory_node = contains_parent
            sibling_parent = contains_parent
    else:
        sibling_parent = None

    siblings = []
    if sibling_parent:
        siblings = [
            {"id": target.removeprefix("page:"), "title": graph.nodes[target].get("title", "")}
            for _, target, edge in graph.out_edges(sibling_parent, data=True)
            if edge.get("type") == "contains" and graph.nodes[target].get("type") == "page" and target != node
        ]

    widgets = [
        dict(graph.nodes[target])
        for _, target, edge in graph.out_edges(node, data=True)
        if edge.get("type") == "has_widget"
    ]
    filters = get_valid_filters(page_id)
    directory = dict(graph.nodes[directory_node]) if directory_node else None
    return {
        "page": page,
        "directory": directory,
        "siblings": siblings,
        "similar_pages": _similar_pages(page_id),
        "widgets": widgets,
        "filters": filters,
    }


def get_valid_filters(page_id: str) -> list[dict[str, Any]]:
    page = _page_data(page_id)
    if page is None:
        return []
    return [
        {
            "name": filter_data.get("name"),
            "type": filter_data.get("type"),
            "allowed_values": list(filter_data.get("allowed_values") or []),
            "default": filter_data.get("default", filter_data.get("default_value")),
        }
        for filter_data in (page.get("filters") or [])
        if filter_data.get("name")
    ]


def _validation(valid: bool, reason: str, suggestions: list[str] | None = None) -> dict[str, Any]:
    return {"valid": valid, "reason": reason, "suggestions": suggestions or []}


def _closest(text: str, candidates: list[str], limit: int = 3) -> list[str]:
    if not text or not candidates:
        return []
    normalized = {_normalise(candidate): candidate for candidate in candidates}
    matches = difflib.get_close_matches(_normalise(text), list(normalized), n=limit, cutoff=0.35)
    return [normalized[match] for match in matches]


def is_valid_filter(page_id: str, name: str, value: Any) -> dict[str, Any]:
    page = _page_data(page_id)
    if page is None:
        return _validation(False, f"Unknown page '{page_id}'")
    filters = {str(item.get("name")): item for item in (page.get("filters") or []) if item.get("name")}
    if name not in filters:
        return _validation(False, f"Unknown filter '{name}' for page '{page_id}'", _closest(name, list(filters)))
    if value is None or value == "":
        return _validation(True, "No filter value selected")

    definition = filters[name]
    allowed = [str(item) for item in (definition.get("allowed_values") or [])]
    values = value if isinstance(value, list) else [value]
    valid_values = {item.casefold() for item in allowed}
    invalid = [item for item in values if str(item).casefold() not in valid_values]
    if not invalid:
        return _validation(True, "Filter value is allowed")
    suggestions = _closest(str(invalid[0]), allowed)
    return _validation(False, f"Invalid value for filter '{name}': {invalid[0]}", suggestions)


def is_valid_date_range(page_id: str, name: str) -> dict[str, Any]:
    page = _page_data(page_id)
    if page is None:
        return _validation(False, f"Unknown page '{page_id}'")
    options = [str(item) for item in (page.get("date_range_options") or [])]
    if name in options:
        return _validation(True, "Date range is allowed")
    return _validation(False, f"Invalid date range '{name}'", _closest(name, options))


def is_valid_sort(page_id: str, field: str) -> dict[str, Any]:
    page = _page_data(page_id)
    if page is None:
        return _validation(False, f"Unknown page '{page_id}'")
    options = page.get("sort_options") or []
    valid_fields = [option_id for option_id in (_option_id(item) for item in options) if option_id is not None]
    if field in valid_fields:
        return _validation(True, "Sort option is allowed")
    labels = [_option_label(item) for item in options]
    return _validation(False, f"Invalid sort field '{field}'", _closest(field, list(dict.fromkeys(valid_fields + labels))))


def suggest_values(page_id: str, filter_name: str, text: str) -> list[str]:
    page = _page_data(page_id)
    if page is None:
        return []
    definition = next((item for item in (page.get("filters") or []) if item.get("name") == filter_name), None)
    if definition is None:
        return []
    return _closest(text, [str(value) for value in (definition.get("allowed_values") or [])])


def _is_accessible(page: dict[str, Any], role: str) -> bool:
    allowed = page.get("allowed_roles")
    if not allowed:
        return True
    if isinstance(allowed, str):
        allowed = [allowed]
    wanted_roles = {_role_id(role)}
    if _role_id(role) == "regionalmanager":
        wanted_roles.add("analyst")
    return any(_role_id(item.get("id", "") if isinstance(item, dict) else item) in wanted_roles for item in allowed)


def suggest_pages(query_text: str, role: str | None = None, k: int = 5) -> list[dict[str, Any]]:
    if k <= 0:
        return []
    metadata = _metadata()
    pages = [page for page in (metadata.get("pages") or []) if not role or _is_accessible(page, role)]
    page_by_id = {str(page.get("id")): page for page in pages if page.get("id") is not None}
    ranked: list[dict[str, Any]] = []

    try:
        from app.retrieval import search

        retrieved = search(query_text, k=max(k * 4, k), role=role)
        for result in retrieved:
            page_id = str(result.get("page_id", ""))
            if result.get("type") == "page" and page_id in page_by_id and page_id not in {item["id"] for item in ranked}:
                ranked.append({"id": page_id, "title": page_by_id[page_id].get("title", page_id), "score": result.get("score", 0.0)})
    except (ImportError, RuntimeError, ValueError):
        ranked = []

    query = _normalise(query_text)
    fuzzy = []
    for page_id, page in page_by_id.items():
        title = str(page.get("title", page_id))
        candidates = [title, *(str(keyword) for keyword in (page.get("keywords") or []))]
        ratio = max((difflib.SequenceMatcher(None, query, _normalise(candidate)).ratio() for candidate in candidates), default=0.0)
        fuzzy.append((ratio, page_id, title))
    for score, page_id, title in sorted(fuzzy, reverse=True):
        if page_id not in {item["id"] for item in ranked}:
            ranked.append({"id": page_id, "title": title, "score": float(score)})
        if len(ranked) >= k:
            break
    return ranked[:k]


def accessible_pages(role: str) -> list[dict[str, Any]]:
    metadata = _metadata()
    return [
        {
            "id": str(page.get("id")),
            "title": page.get("title", ""),
            "region_scoped": bool(page.get("region_scoped", False)),
        }
        for page in (metadata.get("pages") or [])
        if page.get("id") is not None and _is_accessible(page, role)
    ]


def role_region_scope(role: str) -> str | None:
    return "South" if _role_id(role) == "regionalmanager" else None


def pages_with_filter(filter_name: str) -> list[dict[str, str]]:
    metadata = _metadata()
    return [
        {"id": str(page.get("id")), "title": str(page.get("title", ""))}
        for page in (metadata.get("pages") or [])
        if page.get("id") is not None and any(item.get("name") == filter_name for item in (page.get("filters") or []))
    ]


def enrich_search_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    graph = get_graph()
    enriched = []
    for result in results:
        page_id = str(result.get("page_id", ""))
        page = _page_data(page_id)
        if page is None:
            enriched.append(dict(result))
            continue
        directory_id = str(page.get("directory", ""))
        directory = graph.nodes.get(f"directory:{directory_id}", {}).get("title", directory_id)
        enriched.append({
            **result,
            "breadcrumb": " / ".join(get_breadcrumb(page_id)),
            "directory": directory,
            "similar_pages": [{"id": item["id"], "title": item["title"]} for item in _similar_pages(page_id)],
            "valid_filters": [item["name"] for item in get_valid_filters(page_id)],
        })
    return enriched
