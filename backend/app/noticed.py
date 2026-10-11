from __future__ import annotations

from typing import Any
from app.apps import get_active_app_id
from app.analysis.engine import get_engine, find_contributors, investigate

_NOTICED_CACHE: dict[str, dict[str, Any]] = {}


def compute_noticed(app_id: str | None = None, role: str = "admin") -> dict[str, Any]:
    active_id = app_id or get_active_app_id()
    if active_id in _NOTICED_CACHE:
        return _NOTICED_CACHE[active_id]

    eng = get_engine()
    cat = eng.catalog
    metrics = cat.list_metrics()
    dims = cat.list_dimensions()

    if not metrics or not dims:
        return {}

    # The primary metric of the app is the first metric (revenue for meridian, appointments for clinic)
    primary_metric = metrics[0]

    all_candidates: list[dict[str, Any]] = []

    # Check primary metric first, then other metrics if primary metric has no drops
    metric_order = [primary_metric] + [m for m in metrics if m.id != primary_metric.id]

    for m in metric_order:
        m_candidates = []
        is_count = m.format == "count" or m.id in ("appointments", "orders", "units")
        for d in dims:
            try:
                res = find_contributors(m.id, d.id, "this_quarter", role=role)
                contributors = res.get("result", {}).get("contributors", [])
                for c in contributors:
                    pct = c.get("pct_change") if c.get("pct_change") is not None else c.get("percent_change")
                    chg = float(c.get("change", 0.0))
                    if pct is not None:
                        if is_count:
                            fmt_chg = f"{chg:+.0f}" if chg != 0 else "0"
                        else:
                            fmt_chg = c.get("formatted_change") or (f"-${abs(chg):,.2f}" if chg < 0 else f"${chg:,.2f}")
                        m_candidates.append({
                            "metric": m.id,
                            "metric_label": m.label,
                            "dimension": d.id,
                            "dimension_label": d.label,
                            "segment": str(c.get("label")),
                            "change": chg,
                            "percent_change": float(pct),
                            "formatted_change": fmt_chg,
                            "formatted_pct_change": c.get("formatted_pct_change") or f"{pct:+.1f}%",
                        })
            except Exception:
                continue

        all_candidates.extend(m_candidates)
        metric_drops = [c for c in m_candidates if c["percent_change"] < 0]
        if metric_drops:
            break

    drops = [c for c in all_candidates if c["percent_change"] < 0]
    drops_sorted = sorted(drops, key=lambda x: (x["percent_change"], -abs(x["change"])))

    if drops_sorted:
        winner = drops_sorted[0]
        direction = "drop"
    elif all_candidates:
        risers = sorted(all_candidates, key=lambda x: (x["percent_change"], abs(x["change"])), reverse=True)
        winner = risers[0]
        direction = "rise"
    else:
        winner = {
            "metric": primary_metric.id,
            "metric_label": primary_metric.label,
            "dimension": dims[0].id if dims else "dimension",
            "segment": "All",
            "change": 0.0,
            "percent_change": 0.0,
            "formatted_change": "$0",
            "formatted_pct_change": "0.0%",
        }
        direction = "neutral"

    top_contributors: list[dict[str, Any]] = []
    baseline: dict[str, Any] = {}
    is_count_metric = winner["metric"] in ("appointments", "orders", "units") or cat.get_metric(winner["metric"]).format == "count"

    try:
        inv = investigate(
            winner["metric"],
            "this_quarter",
            "previous_period",
            filters={winner["dimension"]: winner["segment"]},
            max_depth=2,
            role=role,
        )
        baseline = inv.get("result", {}).get("baseline", {})
        top_dims = inv.get("result", {}).get("top_dimensions", [])
        for td in top_dims:
            for c in td.get("contributors", []):
                lbl = c.get("label")
                if lbl and lbl != winner["segment"] and len(top_contributors) < 2:
                    c_pct = c.get("pct_change") if c.get("pct_change") is not None else c.get("percent_change")
                    chg_val = float(c.get("change", 0.0))
                    if is_count_metric:
                        fmt_c = f"{chg_val:+.0f}"
                    else:
                        fmt_c = c.get("formatted_change") or (f"-${abs(chg_val):,.2f}" if chg_val < 0 else f"${chg_val:,.2f}")
                    top_contributors.append({
                        "label": lbl,
                        "change": chg_val,
                        "percent_change": c_pct,
                        "formatted_change": fmt_c,
                    })
    except Exception:
        pass

    m_lbl = winner["metric_label"]
    seg = winner["segment"]
    pct_val = winner["percent_change"]
    pct_str = winner["formatted_pct_change"]
    chg_str = winner["formatted_change"]

    cur_str = baseline.get("formatted_current") or (f"{baseline.get('current_value', 0):,.0f}" if is_count_metric else f"${baseline.get('current_value', 0):,.2f}")
    prev_str = baseline.get("formatted_previous") or (f"{baseline.get('previous_value', 0):,.0f}" if is_count_metric else f"${baseline.get('previous_value', 0):,.2f}")

    verb = "fell" if direction == "drop" else "rose"

    if cur_str and prev_str:
        sentence = f"{seg} {m_lbl.lower()} {verb} by {chg_str} ({pct_str}) from {prev_str} to {cur_str}"
    else:
        sentence = f"{seg} {m_lbl.lower()} {verb} by {chg_str} ({pct_str}) vs previous quarter"

    if top_contributors:
        contrib_phrases = [
            f"{tc['label']} ({tc['formatted_change']})" if tc.get('formatted_change') else tc['label']
            for tc in top_contributors[:2]
        ]
        sentence += f", led by {' and '.join(contrib_phrases)}."
    else:
        sentence += "."

    chips = [
        f"Why did {seg} {m_lbl.lower()} drop?" if direction == "drop" else f"Why did {seg} {m_lbl.lower()} rise?",
        f"Show {seg} {m_lbl.lower()} trend",
    ]

    # Build up to 5 insights (largest drops and rises vs previous quarter)
    insights: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    ranked_candidates = drops_sorted[:3] + [c for c in sorted(all_candidates, key=lambda x: (x["percent_change"], abs(x["change"])), reverse=True) if c["percent_change"] > 0][:3]
    if not ranked_candidates and all_candidates:
        ranked_candidates = sorted(all_candidates, key=lambda x: abs(x.get("percent_change", 0.0)), reverse=True)[:5]

    for c in ranked_candidates:
        key = f"{c['metric']}_{c['dimension']}_{c['segment']}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        v = "fell" if c["percent_change"] < 0 else "rose"
        q_verb = "drop" if c["percent_change"] < 0 else "rise"
        insights.append({
            "id": key,
            "title": f"{c['segment']} {c['metric_label']} {v} {c['formatted_pct_change']}",
            "description": f"{c['formatted_change']} vs previous quarter ({c.get('dimension_label', c['dimension'])})",
            "question": f"Why did {c['segment']} {c['metric_label'].lower()} {q_verb} this quarter?",
            "direction": "drop" if c["percent_change"] < 0 else "rise",
            "percent_change": c["percent_change"],
            "formatted_change": c["formatted_change"],
            "formatted_pct_change": c["formatted_pct_change"],
        })
        if len(insights) >= 5:
            break

    result = {
        "app_id": active_id,
        "metric": winner["metric"],
        "metric_label": m_lbl,
        "dimension": winner["dimension"],
        "segment": seg,
        "direction": direction,
        "headline": f"{seg} {m_lbl} {verb} by {pct_str}",
        "sentence": sentence,
        "formatted_change": chg_str,
        "percent_change": pct_val,
        "formatted_pct_change": pct_str,
        "current_value": baseline.get("current_value"),
        "previous_value": baseline.get("previous_value"),
        "formatted_current": cur_str,
        "formatted_previous": prev_str,
        "top_contributors": top_contributors,
        "chips": chips,
        "insights": insights,
    }

    _NOTICED_CACHE[active_id] = result
    return result


def clear_noticed_cache() -> None:
    _NOTICED_CACHE.clear()
