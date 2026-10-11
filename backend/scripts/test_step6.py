from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure offline mode for sentence-transformers and Gemini in tests
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["OFFLINE_TESTS"] = "1"

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.agent import run_agent
from app.analysis.catalog import get_metric, list_metrics
from app.analysis.engine import investigate
from app.apps import get_active_app_id, select_app
from app.languages import detect_language, normalize_with_lexicon
from app.retrieval import search
from app.suggestions import generate_suggestions
from scripts.import_app import import_app, validate_metadata


def report(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    msg = f"{status}: {name}"
    if detail:
        msg += f" - {detail}"
    print(msg)
    return passed


def test_language_detection() -> bool:
    checks = []
    # English
    en_res = detect_language("What is total revenue for South region?")
    checks.append(report("language detection English", en_res == "en", f"got {en_res}"))

    # Hindi script (Devanagari)
    hi_res = detect_language("दक्षिण क्षेत्र में कुल बिक्री कितनी है?")
    checks.append(report("language detection Hindi Devanagari", hi_res == "hi", f"got {hi_res}"))

    # Kannada script
    kn_res = detect_language("ದಕ್ಷಿಣ ಪ್ರದೇಶದಲ್ಲಿ ಒಟ್ಟು ಆದಾಯ ಎಷ್ಟು?")
    checks.append(report("language detection Kannada script", kn_res == "kn", f"got {kn_res}"))

    # Mixed (Devanagari dominant)
    mixed_res = detect_language("South क्षेत्र में revenue गिरावट क्यों हुई?")
    checks.append(report("language detection mixed dominant script", mixed_res == "hi", f"got {mixed_res}"))

    # Romanized Hindi
    roma_hi = detect_language("South me bikri kitna drop hua")
    checks.append(report("language detection romanized Hindi", roma_hi == "hi", f"got {roma_hi}"))

    # Romanized Kannada
    roma_kn = detect_language("South pradeshadalli eshtu adayam")
    checks.append(report("language detection romanized Kannada", roma_kn == "kn", f"got {roma_kn}"))

    return all(checks)


def test_lexicon_normalization() -> bool:
    checks = []
    # Hindi mapping
    hi_q = "दक्षिण में इस तिमाही बिक्री में गिरावट क्यों हुई?"
    hi_norm = normalize_with_lexicon(hi_q)
    has_hi_terms = (
        "South" in hi_norm
        and "quarter" in hi_norm
        and "revenue" in hi_norm
        and "drop" in hi_norm
    )
    checks.append(report("lexicon normalization Hindi to English", has_hi_terms, f"normalized: '{hi_norm}'"))

    # Kannada mapping
    kn_q = "ಉತ್ತರ ಪ್ರದೇಶದಲ್ಲಿ ಈ ತ್ರೈಮಾಸಿಕ ಆದಾಯದಲ್ಲಿ ಇಳಿಕೆ ಏಕೆ?"
    kn_norm = normalize_with_lexicon(kn_q)
    has_kn_terms = (
        "North" in kn_norm
        and "quarter" in kn_norm
        and "revenue" in kn_norm
        and "drop" in kn_norm
    )
    checks.append(report("lexicon normalization Kannada to English", has_kn_terms, f"normalized: '{kn_norm}'"))

    return all(checks)


def test_suggestions() -> bool:
    checks = []
    select_app("meridian")
    meta = json.loads((ROOT / "data" / "app_metadata.json").read_text(encoding="utf-8"))
    all_pages = meta["pages"]
    page1_id = all_pages[0]["id"]
    page2_id = all_pages[1]["id"]
    admin_only_id = next(p["id"] for p in all_pages if p.get("allowed_roles") == ["admin"])

    # Suggestion chips for page 1
    chips1 = generate_suggestions(page1_id, role="admin")
    has_3_chips1 = len(chips1) == 3 and all(isinstance(c, str) and len(c) > 5 for c in chips1)
    checks.append(report(
        "suggestions for page 1 return 3 valid chips with metrics",
        has_3_chips1,
        f"page: {page1_id}, chips: {chips1}",
    ))

    # Suggestion chips for page 2
    chips2 = generate_suggestions(page2_id, role="admin")
    has_3_chips2 = len(chips2) == 3 and all(isinstance(c, str) and len(c) > 5 for c in chips2)
    checks.append(report(
        "suggestions for page 2 return 3 valid chips with metrics",
        has_3_chips2,
        f"page: {page2_id}, chips: {chips2}",
    ))

    # Restricted role cannot see admin-only page
    chips_restricted = generate_suggestions(admin_only_id, role="analyst")
    checks.append(report(
        "restricted role does not get chips for unauthorized page",
        len(chips_restricted) == 0,
        f"page: {admin_only_id}, got: {chips_restricted}",
    ))

    return all(checks)


def test_importer_and_clinic_metadata() -> bool:
    checks = []
    clinic_meta_path = ROOT / "data" / "apps" / "clinic" / "app_metadata.json"
    clinic_meta = json.loads(clinic_meta_path.read_text(encoding="utf-8"))

    # 1. 15 pages in total
    pages = clinic_meta.get("pages", [])
    has_15_pages = len(pages) == 15
    checks.append(report(
        "clinic metadata has exactly 15 pages",
        has_15_pages,
        f"found {len(pages)} pages",
    ))

    # 2. 3 sections (Overview, Departments, Operations)
    directories = clinic_meta.get("directories", [])
    dir_ids = {d["id"] for d in directories}
    has_3_sections = {"overview", "departments", "operations"}.issubset(dir_ids)
    checks.append(report(
        "clinic metadata has 3 sections (overview, departments, operations)",
        has_3_sections,
        f"found directories: {dir_ids}",
    ))

    # 3. Widget count around 40
    total_widgets = sum(len(p.get("widgets", [])) for p in pages)
    reasonable_widget_count = 35 <= total_widgets <= 45
    checks.append(report(
        "clinic metadata has around 40 widgets (~43)",
        reasonable_widget_count,
        f"found {total_widgets} widgets across 15 pages",
    ))

    # 4. Importer accepts valid clinic app metadata
    imported = import_app(clinic_meta_path)
    checks.append(report("importer accepts valid expanded clinic metadata", imported))

    # 5. Broken metadata rejected
    broken_meta = {
        "app": {"name": "Broken App"},  # missing id
        "pages": []                      # empty pages
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(broken_meta, f)
        temp_path = f.name

    try:
        errors = validate_metadata(broken_meta)
        rejected = not import_app(temp_path)
        checks.append(report(
            "importer rejects broken file with clear errors",
            rejected and len(errors) > 0,
            f"errors found: {errors}",
        ))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return all(checks)


def test_clinic_orthopedics_investigation() -> bool:
    checks = []
    select_app("clinic")

    # 1. Direct analysis engine investigation
    inv = investigate(
        metric="appointments",
        period="this_quarter",
        compare_to="previous_period",
        filters={"department": "Orthopedics"},
        max_depth=3,
        role="admin",
    )
    result = inv.get("result", {})
    baseline = result.get("baseline", {})
    pct_change = baseline.get("percent_change", 0.0)

    # Orthopedics appointments fell about 20%
    shows_decline = pct_change < 0 and abs(pct_change - (-20.0)) < 1.0
    checks.append(report(
        "Orthopedics appointments fell about 20 percent this quarter",
        shows_decline,
        f"percent_change: {pct_change}%, baseline: {baseline}",
    ))

    # Follow-up among steepest drops
    steepest_decliners = result.get("steepest_decliners", [])
    has_followup_drop = any(d.get("label") == "Follow-up" for d in steepest_decliners)
    checks.append(report(
        "investigation shows Follow-up among the steepest drops",
        has_followup_drop,
        f"steepest_decliners: {steepest_decliners}",
    ))

    # 2. Agent investigation query
    agent_res = run_agent("Why did Orthopedics appointments change this quarter?", role="admin")
    agent_answered = agent_res.get("outcome") == "answered"
    agent_analysis = agent_res.get("analysis", {})
    agent_steepest = agent_analysis.get("steepest_decliners", [])
    agent_has_followup = any(d.get("label") == "Follow-up" for d in agent_steepest)

    checks.append(report(
        "agent handles 'Why did Orthopedics appointments change this quarter?'",
        agent_answered and agent_has_followup,
        f"outcome: {agent_res.get('outcome')}, steepest: {agent_steepest}",
    ))

    return all(checks)


def test_clinic_revenue_refusal() -> bool:
    checks = []
    select_app("clinic")

    # 1. Catalog verification: revenue must NOT exist
    has_no_revenue_metric = get_metric("revenue") is None
    all_clinic_metrics = [m.id for m in list_metrics()]
    no_revenue_in_catalog = "revenue" not in all_clinic_metrics and "fee_revenue" not in all_clinic_metrics
    checks.append(report(
        "clinic analysis catalog does NOT contain 'revenue'",
        has_no_revenue_metric and no_revenue_in_catalog,
        f"clinic metrics: {all_clinic_metrics}",
    ))

    # 2. Agent refuses "revenue" question on clinic app
    rev_q1 = run_agent("What is total revenue this quarter?", role="admin")
    refused1 = rev_q1.get("outcome") in ("refused", "error") and (
        rev_q1.get("reason") == "not_in_app" or rev_q1.get("refusal_reason") == "not_in_app"
    )
    checks.append(report(
        "revenue question on clinic app is refused (reason=not_in_app)",
        refused1,
        f"outcome: {rev_q1.get('outcome')}, reason: {rev_q1.get('reason') or rev_q1.get('refusal_reason')}",
    ))

    rev_q2 = run_agent("Why did revenue change this quarter?", role="admin")
    refused2 = rev_q2.get("outcome") in ("refused", "error") and (
        rev_q2.get("reason") == "not_in_app" or rev_q2.get("refusal_reason") == "not_in_app"
    )
    checks.append(report(
        "why did revenue change on clinic app is refused (reason=not_in_app)",
        refused2,
        f"outcome: {rev_q2.get('outcome')}, reason: {rev_q2.get('reason') or rev_q2.get('refusal_reason')}",
    ))

    return all(checks)


def test_retrieval_isolation() -> bool:
    checks = []

    # 1. Clinic app retrieval: "no-show analysis" returns No-show Analysis page
    select_app("clinic")
    noshow_results = search("no-show analysis", k=5)
    has_noshow_page = bool(noshow_results) and noshow_results[0].get("page_id") == "no_show_analysis"
    checks.append(report(
        "retrieval for 'no-show analysis' returns No-show Analysis page (no_show_analysis)",
        has_noshow_page,
        f"top result: {noshow_results[0] if noshow_results else None}",
    ))

    clinic_results = search("doctor appointments overview schedule", k=5)
    meta = json.loads((ROOT / "data" / "apps" / "clinic" / "app_metadata.json").read_text(encoding="utf-8"))
    clinic_page_ids = {p["id"] for p in meta["pages"]}
    all_clinic = bool(clinic_results) and all(r["page_id"] in clinic_page_ids for r in clinic_results)
    checks.append(report(
        "retrieval on clinic app returns clinic pages only",
        all_clinic,
        f"found page_ids: {[r['page_id'] for r in clinic_results]}",
    ))

    # 2. Sales app retrieval unchanged
    select_app("meridian")
    sales_results = search("revenue by region product channel", k=5)
    all_sales = bool(sales_results) and all(r["page_id"] not in clinic_page_ids for r in sales_results)
    checks.append(report(
        "sales app retrieval unchanged and isolated from clinic",
        all_sales,
        f"found page_ids: {[r['page_id'] for r in sales_results]}",
    ))

    return all(checks)


def main() -> None:
    print("=== STEP 6 / 6B TEST SUITE ===")
    results = [
        test_language_detection(),
        test_lexicon_normalization(),
        test_suggestions(),
        test_importer_and_clinic_metadata(),
        test_clinic_orthopedics_investigation(),
        test_clinic_revenue_refusal(),
        test_retrieval_isolation(),
    ]

    all_passed = all(results)
    print("\n=========================")
    if all_passed:
        print("ALL STEP 6 / 6B TESTS PASSED")
        sys.exit(0)
    else:
        print("STEP 6 / 6B TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
