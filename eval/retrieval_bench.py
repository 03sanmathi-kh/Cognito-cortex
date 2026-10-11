from __future__ import annotations

import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

# Force offline mode for sentence-transformers
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.languages import normalize_with_lexicon
from app.retrieval import _tokens, _get_model
from eval.metrics import precision_at_k, recall_at_k, reciprocal_rank

_RRF_CONSTANT = 60


def build_synthetic_catalog(seed: int = 42) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate 300+ deterministic components and 60+ benchmark queries."""
    rng = random.Random(seed)

    base_components = [
        ("Revenue by Region", "Sales / Regional / Revenue", "page", "revenue sales income earnings north south east west distribution"),
        ("Top Products by Region", "Sales / Products / Volume", "page", "top selling products units quantity merchandise sales performance"),
        ("Order Volume and Velocity", "Operations / Orders / Velocity", "page", "daily order processing intake velocity throughput packaging SLA"),
        ("Channel Mix by Region", "Sales / Channels / Performance", "page", "online retail partner channel distribution share of revenue"),
        ("Gross Margin by Category", "Finance / Margin / Product", "page", "gross profit margin percentage cost of goods sold product profitability"),
        ("Operating Expenses Breakdown", "Finance / Expenses / Operating", "page", "operating expenses opex payroll facilities freight variance costs"),
        ("Inventory Stock by Region", "Inventory / Stock / Regional", "page", "warehouse inventory stock on hand days of cover stockout safety stock"),
        ("Repeat Purchase Rate", "Customers / Retention / Loyalty", "page", "repeat purchase customer loyalty second order rate frequency cohorts"),
        ("Customer Lifetime Value", "Customers / Value / CLV", "page", "customer lifetime value clv average order value enterprise smb retention"),
        ("Warehouse Capacity Utilization", "Operations / Warehouse / Utilization", "page", "warehouse capacity storage utilization pallets square feet facility"),
        ("Shipping Performance by Region", "Operations / Logistics / Shipping", "page", "on time in full delivery carrier transit lead time shipping performance"),
        ("Purchase Order Backlog", "Inventory / Purchasing / Backlog", "page", "supplier purchase orders po backlog open vendor delivery eta"),
        ("User Access Overview", "Admin / Security / Users", "page", "user roles permissions security access audit admin analyst manager"),
        ("Audit Log Activity", "Admin / Audit / Security", "page", "system audit trail security log login events admin user actions"),
        ("Clinic Overview", "Clinic / Operations / Overview", "page", "clinic overview appointments status doctor schedule attendance visits"),
        ("Appointments Trend", "Clinic / Appointments / Trend", "page", "appointments volume time series daily weekly trend clinic visits"),
        ("No-show Analysis", "Clinic / Patients / Attendance", "page", "no show rate missed appointments patient attendance follow up"),
        ("Cancellations Page", "Clinic / Appointments / Cancellations", "page", "appointment cancellations cancelled booking cancellation reasons"),
        ("Doctor Workload", "Clinic / Staff / Workload", "page", "doctor consulting workload wait times daily patient quota"),
        ("Fee Collection Page", "Clinic / Finance / Billing", "page", "clinic fee revenue billing collection patient consulting payments"),
    ]

    metrics = [
        ("revenue", "net sales dollar turnover commercial proceeds"),
        ("orders", "completed purchases transaction checkout count volume"),
        ("units", "quantity count volume pieces physical cartons"),
        ("margin", "profitability spread gross margin financial return"),
        ("expenses", "overhead spending expenditure freight operations cost"),
        ("inventory", "stock reserves storage warehouse holdings replenishment"),
        ("lead_time", "fulfillment speed delivery transit dispatch velocity"),
        ("churn", "customer attrition loss risk retention departure"),
        ("appointments", "consulting consultations doctor bookings clinic visits"),
        ("wait_time", "patient waiting delay registration consultation minutes"),
    ]

    regions_or_depts = [
        ("North", "northern territory division zone hub"),
        ("South", "southern territory division zone hub"),
        ("East", "eastern territory division zone hub"),
        ("West", "western territory division zone hub"),
        ("Central", "central territory division zone hub"),
        ("Cardiology", "heart cardiac cardiology specialist coronary"),
        ("Dermatology", "skin dermatology specialist cutaneous dermal"),
        ("Pediatrics", "children child infant pediatric youth"),
        ("Orthopedics", "bones skeletal joint orthopedic fracture spine"),
        ("General Medicine", "primary general medicine physician consultation health"),
    ]

    products_or_doctors = [
        ("Granola Crunch Cereal", "packaged breakfast food grain crunch"),
        ("Organic Pasta Sauce", "packaged food organic tomato pasta sauce"),
        ("Artisan Roasted Nuts", "packaged food snack artisan roasted nuts"),
        ("Sparkling Spring Water", "beverages water sparkling mineral refreshment"),
        ("Cold Brew Coffee", "beverages cold brew roast caffeinated drink"),
        ("Citrus Electrolyte Tea", "beverages herbal tea citrus electrolyte beverage"),
        ("Eco Dish Soap", "household cleaning detergent eco biodegradable soap"),
        ("Multi-Surface Spray", "household disinfectant surface cleaner spray"),
        ("Recycled Paper Towels", "household paper towels absorbent wipes kitchen"),
        ("Hydrating Herbal Lotion", "personal care cosmetic herbal moisturizing cream"),
        ("Dr. Sharma", "senior consultant physician dr sharma"),
        ("Dr. Rao", "specialist clinician dr rao"),
        ("Dr. Patel", "attending physician dr patel"),
        ("Dr. Mehta", "consulting doctor dr mehta"),
        ("Dr. Nair", "specialist doctor dr nair"),
    ]

    comp_types = ["page", "kpi", "chart", "grid", "widget"]

    components: list[dict[str, Any]] = []
    idx = 0

    # 1. Base components
    for title, breadcrumb, c_type, text in base_components:
        components.append({
            "id": f"comp_{idx:03d}",
            "title": title,
            "breadcrumb": breadcrumb,
            "type": c_type,
            "text": f"{breadcrumb} {title} {c_type} {text}",
        })
        idx += 1

    # 2. Permutation components to reach 320+ components
    for met, met_text in metrics:
        for reg, reg_text in regions_or_depts:
            for prod, prod_text in products_or_doctors[:3]:
                c_type = rng.choice(comp_types)
                title = f"{reg} {met.title()} for {prod}"
                breadcrumb = f"Analytics / {reg} / {met.title()}"
                text = f"{breadcrumb} {title} {c_type} {met_text} {reg_text} {prod_text}"
                components.append({
                    "id": f"comp_{idx:03d}",
                    "title": title,
                    "breadcrumb": breadcrumb,
                    "type": c_type,
                    "text": text,
                })
                idx += 1
                if idx >= 320:
                    break
            if idx >= 320:
                break
        if idx >= 320:
            break

    # Ground-truth benchmark queries (64 queries with known correct component IDs)
    queries: list[dict[str, Any]] = [
        # English exact & keyword queries
        {"query": "Revenue by Region", "target_id": "comp_000"},
        {"query": "Top Products by Region", "target_id": "comp_001"},
        {"query": "Order Volume and Velocity", "target_id": "comp_002"},
        {"query": "Channel Mix by Region", "target_id": "comp_003"},
        {"query": "Gross Margin by Category", "target_id": "comp_004"},
        {"query": "Operating Expenses Breakdown", "target_id": "comp_005"},
        {"query": "Inventory Stock by Region", "target_id": "comp_006"},
        {"query": "Repeat Purchase Rate", "target_id": "comp_007"},
        {"query": "Customer Lifetime Value", "target_id": "comp_008"},
        {"query": "Warehouse Capacity Utilization", "target_id": "comp_009"},
        {"query": "Shipping Performance by Region", "target_id": "comp_010"},
        {"query": "Purchase Order Backlog", "target_id": "comp_011"},
        {"query": "User Access Overview", "target_id": "comp_012"},
        {"query": "Audit Log Activity", "target_id": "comp_013"},
        {"query": "Clinic Overview", "target_id": "comp_014"},
        {"query": "Appointments Trend", "target_id": "comp_015"},
        {"query": "No-show Analysis", "target_id": "comp_016"},
        {"query": "Cancellations Page", "target_id": "comp_017"},
        {"query": "Doctor Workload", "target_id": "comp_018"},
        {"query": "Fee Collection Page", "target_id": "comp_019"},

        # English natural paraphrases & semantic searches
        {"query": "where can I check money earned across territories", "target_id": "comp_000"},
        {"query": "which items sell the fastest in southern territories", "target_id": "comp_001"},
        {"query": "daily package throughput and processing speeds", "target_id": "comp_002"},
        {"query": "sales distribution across online and retail partners", "target_id": "comp_003"},
        {"query": "profit margins across product lines and cogs", "target_id": "comp_004"},
        {"query": "logistics freight and payroll overhead spending", "target_id": "comp_005"},
        {"query": "warehouse stock levels and stockout prevention days", "target_id": "comp_006"},
        {"query": "customer loyalty second order retention frequency", "target_id": "comp_007"},
        {"query": "long term clv value of enterprise and smb buyers", "target_id": "comp_008"},
        {"query": "storage space pallet capacity utilization in warehouses", "target_id": "comp_009"},
        {"query": "on-time in-full delivery performance metrics", "target_id": "comp_010"},
        {"query": "open supplier orders waiting for fulfillment eta", "target_id": "comp_011"},
        {"query": "security access permissions role matrix", "target_id": "comp_012"},
        {"query": "audit trail log of user login actions", "target_id": "comp_013"},
        {"query": "general medical clinic appointments schedule", "target_id": "comp_014"},
        {"query": "patient visit trends over time in clinic", "target_id": "comp_015"},

        # Hindi queries (with lexicon normalization)
        {"query": "क्षेत्र के अनुसार राजस्व", "target_id": "comp_000"},
        {"query": "दक्षिण क्षेत्र में राजस्व दिखाओ", "target_id": "comp_000"},
        {"query": "उत्तर क्षेत्र की बिक्री दिखाओ", "target_id": "comp_000"},
        {"query": "शीर्ष उत्पाद पृष्ठ पर जाओ", "target_id": "comp_001"},
        {"query": "ऑर्डर वॉल्यूम पृष्ठ खोलो", "target_id": "comp_002"},
        {"query": "माध्यम और चैनल प्रदर्शन", "target_id": "comp_003"},
        {"query": "खर्च और लागत का विवरण", "target_id": "comp_005"},
        {"query": "इलाके में इन्वेंटरी और स्टॉक", "target_id": "comp_006"},
        {"query": "ग्राहक दोहराव खरीद दर", "target_id": "comp_007"},
        {"query": "गोदाम क्षमता और भंडारण", "target_id": "comp_009"},
        {"query": "डिलीवरी और शिपिंग प्रदर्शन", "target_id": "comp_010"},
        {"query": "सुरक्षा और उपयोगकर्ता पहुंच", "target_id": "comp_012"},
        {"query": "क्लिनिक अवलोकन और डॉक्टर", "target_id": "comp_014"},
        {"query": "अपॉइंटमेंट ट्रेंड और रुझान", "target_id": "comp_015"},

        # Kannada queries (with lexicon normalization)
        {"query": "ಪ್ರದೇಶದ ಪ್ರಕಾರ ಆದಾಯ", "target_id": "comp_000"},
        {"query": "ದಕ್ಷಿಣ ವಲಯದ ಮಾರಾಟ ತೋರಿಸಿ", "target_id": "comp_000"},
        {"query": "ಉತ್ತರ ವಲಯದ ಆದಾಯ", "target_id": "comp_000"},
        {"query": "ಟಾಪ್ ಪ್ರಾಡಕ್ಟ್ಸ್ ಪುಟ", "target_id": "comp_001"},
        {"query": "ಆರ್ಡರ್ ವಾಲ್ಯೂಮ್ ಮತ್ತು ವೇಗ", "target_id": "comp_002"},
        {"query": "ಚಾನೆಲ್ ಮಾರಾಟ ಹಂಚಿಕೆ", "target_id": "comp_003"},
        {"query": "ಕಾರ್ಯಾಚರಣೆ ವೆಚ್ಚ ಮತ್ತು ಖರ್ಚು", "target_id": "comp_005"},
        {"query": "ದಾಸ್ತಾನು ಸಂಗ್ರಹ ಮತ್ತು ಸ್ಟಾಕ್", "target_id": "comp_006"},
        {"query": "ಮರು ಖರೀದಿ ದರ ಮತ್ತು ನಿಷ್ಠೆ", "target_id": "comp_007"},
        {"query": "ಗೋದಾಮಿನ ಸಾಮರ್ಥ್ಯ ಬಳಕೆ", "target_id": "comp_009"},
        {"query": "ಶಿಪ್ಪಿಂಗ್ ಮತ್ತು ಡೆಲಿವರಿ ಕಾರ್ಯಕ್ಷಮತೆ", "target_id": "comp_010"},
        {"query": "ಬಳಕೆದಾರ ಪ್ರವೇಶ ಭದ್ರತೆ", "target_id": "comp_012"},
        {"query": "ಕ್ಲಿನಿಕ್ ಅವಲೋಕನ ಮತ್ತು ವೈದ್ಯರು", "target_id": "comp_014"},
        {"query": "ನೇಮಕಾತಿಗಳ ಪ್ರವೃತ್ತಿ ಮತ್ತು ಟ್ರೆಂಡ್", "target_id": "comp_015"},
    ]

    return components, queries


def run_benchmark(seed: int = 42) -> dict[str, Any]:
    """Execute keyword BM25, semantic FAISS, and hybrid RRF benchmark."""
    components, queries = build_synthetic_catalog(seed)
    total_docs = len(components)

    # 1. Build BM25 Index
    t0 = time.perf_counter()
    corpus_tokens = [_tokens(c["text"]) for c in components]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_index_time = time.perf_counter() - t0

    # 2. Build FAISS Index
    t0 = time.perf_counter()
    model = _get_model()
    texts = [c["text"] for c in components]
    embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.asarray(embeddings, dtype=np.float32)
    faiss_index = faiss.IndexFlatIP(embeddings.shape[1])
    faiss_index.add(embeddings)
    faiss_index_time = time.perf_counter() - t0

    hybrid_index_time = bm25_index_time + faiss_index_time

    results = {
        "bm25": {"p1": [], "p5": [], "r5": [], "r10": [], "mrr": [], "latencies_ms": []},
        "faiss": {"p1": [], "p5": [], "r5": [], "r10": [], "mrr": [], "latencies_ms": []},
        "hybrid": {"p1": [], "p5": [], "r5": [], "r10": [], "mrr": [], "latencies_ms": []},
    }

    doc_ids = [c["id"] for c in components]

    # Run queries
    for q_item in queries:
        raw_query = q_item["query"]
        target = q_item["target_id"]

        # Lexicon normalization
        norm_query = normalize_with_lexicon(raw_query)

        # Method 1: BM25
        t_bm25 = time.perf_counter()
        q_tokens = _tokens(norm_query)
        bm25_scores = bm25.get_scores(q_tokens) if q_tokens else np.zeros(total_docs)
        bm25_order = np.argsort(bm25_scores)[::-1]
        bm25_ranked = [doc_ids[i] for i in bm25_order]
        bm25_lat = (time.perf_counter() - t_bm25) * 1000

        results["bm25"]["p1"].append(precision_at_k(bm25_ranked, target, 1))
        results["bm25"]["p5"].append(precision_at_k(bm25_ranked, target, 5))
        results["bm25"]["r5"].append(recall_at_k(bm25_ranked, target, 5))
        results["bm25"]["r10"].append(recall_at_k(bm25_ranked, target, 10))
        results["bm25"]["mrr"].append(reciprocal_rank(bm25_ranked, target))
        results["bm25"]["latencies_ms"].append(bm25_lat)

        # Method 2: FAISS
        t_faiss = time.perf_counter()
        q_emb = model.encode([norm_query], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        _, faiss_indices = faiss_index.search(np.asarray(q_emb, dtype=np.float32), total_docs)
        faiss_ranked = [doc_ids[i] for i in faiss_indices[0] if i >= 0]
        faiss_lat = (time.perf_counter() - t_faiss) * 1000

        results["faiss"]["p1"].append(precision_at_k(faiss_ranked, target, 1))
        results["faiss"]["p5"].append(precision_at_k(faiss_ranked, target, 5))
        results["faiss"]["r5"].append(recall_at_k(faiss_ranked, target, 5))
        results["faiss"]["r10"].append(recall_at_k(faiss_ranked, target, 10))
        results["faiss"]["mrr"].append(reciprocal_rank(faiss_ranked, target))
        results["faiss"]["latencies_ms"].append(faiss_lat)

        # Method 3: Hybrid (RRF)
        t_hybrid = time.perf_counter()
        rrf_scores: dict[int, float] = {}

        # FAISS ranking contribution
        for rank, doc_idx in enumerate(faiss_indices[0], start=1):
            if doc_idx >= 0:
                rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + 1.0 / (_RRF_CONSTANT + rank)

        # BM25 ranking contribution
        for rank, doc_idx in enumerate(bm25_order, start=1):
            if bm25_scores[doc_idx] > 0:
                rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + 1.0 / (_RRF_CONSTANT + rank)

        sorted_indices = sorted(rrf_scores.keys(), key=lambda idx: rrf_scores[idx], reverse=True)
        hybrid_ranked = [doc_ids[i] for i in sorted_indices]
        hybrid_lat = (time.perf_counter() - t_hybrid) * 1000 + faiss_lat

        results["hybrid"]["p1"].append(precision_at_k(hybrid_ranked, target, 1))
        results["hybrid"]["p5"].append(precision_at_k(hybrid_ranked, target, 5))
        results["hybrid"]["r5"].append(recall_at_k(hybrid_ranked, target, 5))
        results["hybrid"]["r10"].append(recall_at_k(hybrid_ranked, target, 10))
        results["hybrid"]["mrr"].append(reciprocal_rank(hybrid_ranked, target))
        results["hybrid"]["latencies_ms"].append(hybrid_lat)

    n_q = len(queries)
    summary = {
        "total_components": total_docs,
        "total_queries": n_q,
        "bm25": {
            "p1": round(sum(results["bm25"]["p1"]) / n_q, 4),
            "p5": round(sum(results["bm25"]["p5"]) / n_q, 4),
            "r5": round(sum(results["bm25"]["r5"]) / n_q, 4),
            "r10": round(sum(results["bm25"]["r10"]) / n_q, 4),
            "mrr": round(sum(results["bm25"]["mrr"]) / n_q, 4),
            "index_time_s": round(bm25_index_time, 3),
            "avg_query_time_ms": round(sum(results["bm25"]["latencies_ms"]) / n_q, 2),
        },
        "faiss": {
            "p1": round(sum(results["faiss"]["p1"]) / n_q, 4),
            "p5": round(sum(results["faiss"]["p5"]) / n_q, 4),
            "r5": round(sum(results["faiss"]["r5"]) / n_q, 4),
            "r10": round(sum(results["faiss"]["r10"]) / n_q, 4),
            "mrr": round(sum(results["faiss"]["mrr"]) / n_q, 4),
            "index_time_s": round(faiss_index_time, 3),
            "avg_query_time_ms": round(sum(results["faiss"]["latencies_ms"]) / n_q, 2),
        },
        "hybrid": {
            "p1": round(sum(results["hybrid"]["p1"]) / n_q, 4),
            "p5": round(sum(results["hybrid"]["p5"]) / n_q, 4),
            "r5": round(sum(results["hybrid"]["r5"]) / n_q, 4),
            "r10": round(sum(results["hybrid"]["r10"]) / n_q, 4),
            "mrr": round(sum(results["hybrid"]["mrr"]) / n_q, 4),
            "index_time_s": round(hybrid_index_time, 3),
            "avg_query_time_ms": round(sum(results["hybrid"]["latencies_ms"]) / n_q, 2),
        },
    }

    return summary


def format_table(summary: dict[str, Any]) -> str:
    """Format retrieval benchmark comparison table."""
    lines = [
        "| Method | Precision@1 | Precision@5 | Recall@5 | Recall@10 | MRR | Index Time (s) | Query Latency (ms) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for key, label in [("bm25", "BM25 (Keyword)"), ("faiss", "FAISS (Semantic)"), ("hybrid", "Hybrid (RRF)")]:
        data = summary[key]
        lines.append(
            f"| {label} | {data['p1']:.3f} | {data['p5']:.3f} | {data['r5']:.3f} | "
            f"{data['r10']:.3f} | {data['mrr']:.3f} | {data['index_time_s']:.3f}s | {data['avg_query_time_ms']:.1f}ms |"
        )
    return "\n".join(lines)


def main() -> None:
    print("Running retrieval benchmark on synthetic 320-component index (64 queries, offline)...")
    summary = run_benchmark()
    print("\n=== Retrieval Benchmark Results ===")
    print(format_table(summary))
    print(f"\nIndexed {summary['total_components']} components; evaluated {summary['total_queries']} queries (En/Hi/Kn).")


if __name__ == "__main__":
    main()
