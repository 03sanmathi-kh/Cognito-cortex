from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from eval.metrics import compute_metrics
from eval.retrieval_bench import run_benchmark, format_table


def find_latest_run(runs_dir: Path) -> Path | None:
    if not runs_dir.exists():
        return None
    jsonl_files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonl_files[0] if jsonl_files else None


def load_run_records(run_path: Path | None) -> list[dict[str, Any]]:
    records = []
    if run_path and run_path.exists():
        with open(run_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
    return records


def build_kpi_table_md(metrics: dict[str, Any]) -> str:
    lines = [
        "| Subset | Count | Task Success | Routing Acc | UI-State Acc | Faithfulness | Abstention | Clarify | Avg Steps | Latency p50 | Latency p95 | Hallucinations |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    def fmt_row(label: str, m: dict[str, Any]) -> str:
        if m.get("count", 0) == 0:
            return f"| {label} | 0 | - | - | - | - | - | - | - | - | - | 0 |"
        return (
            f"| {label} | {m['count']} | {m['task_success_rate']:.1%} | {m['routing_accuracy']:.1%} | "
            f"{m['ui_state_correctness']:.1%} | {m['faithfulness']:.1%} | {m['abstention_correctness']:.1%} | "
            f"{m['clarification_correctness']:.1%} | {m['average_steps']:.1f} | {m['latency_p50_ms']:.0f}ms | "
            f"{m['latency_p95_ms']:.0f}ms | {m['hallucination_count']} |"
        )

    lines.append(fmt_row("**Overall**", metrics["overall"]))
    for sp in ("dev", "heldout"):
        if sp in metrics["by_split"]:
            lines.append(fmt_row(f"Split: {sp}", metrics["by_split"][sp]))
    for lang in ("en", "hi", "kn"):
        if lang in metrics["by_language"]:
            label_map = {"en": "Language: English", "hi": "Language: Hindi", "kn": "Language: Kannada"}
            lines.append(fmt_row(label_map.get(lang, f"Lang: {lang}"), metrics["by_language"][lang]))

    return "\n".join(lines)


def generate_report(
    run_file: Path | None,
    testset_file: Path,
    out_md: Path,
    out_json: Path,
    retrieval_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    testset_data = json.loads(testset_file.read_text(encoding="utf-8")) if testset_file.exists() else []
    total_testset_size = len(testset_data)
    testset_ids = [item["id"] for item in testset_data]

    records = load_run_records(run_file)
    n_run = len(records)
    run_ids = {r["id"] for r in records}
    unrun_ids = [iid for iid in testset_ids if iid not in run_ids]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Metrics
    if n_run > 0:
        metrics = compute_metrics(records)
    else:
        empty_kpi = {
            "count": 0,
            "routing_accuracy": 0.0,
            "ui_state_correctness": 0.0,
            "task_success_rate": 0.0,
            "average_steps": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
            "faithfulness": 0.0,
            "abstention_correctness": 0.0,
            "clarification_correctness": 0.0,
            "hallucination_count": 0,
        }
        metrics = {
            "overall": empty_kpi,
            "by_split": {"dev": empty_kpi, "heldout": empty_kpi},
            "by_group": {},
            "by_language": {"en": empty_kpi, "hi": empty_kpi, "kn": empty_kpi},
            "total_evaluated": 0,
            "failed_items": [],
        }

    # Retrieval benchmark
    if retrieval_summary is None:
        retrieval_summary = run_benchmark()

    # Markdown content
    md_lines = [
        "# Cognito Pilot Evaluation & Benchmark Results",
        "",
        f"- **Date**: {now_str}",
        f"- **Test Set Size**: {total_testset_size} requests (60 sales, 10 clinic)",
        f"- **Items Evaluated**: {n_run} requests",
        "",
        f"**Measured on {n_run} requests; targets are not results.**",
        "",
    ]

    if n_run < total_testset_size:
        md_lines.append(
            f"> [!NOTE]\n"
            f"> **Partial Run Notice**: {n_run} of {total_testset_size} requests have been evaluated. "
            f"{len(unrun_ids)} requests were not run.\n"
        )
        if unrun_ids:
            sample_unrun = ", ".join(unrun_ids[:10])
            if len(unrun_ids) > 10:
                sample_unrun += f", ... ({len(unrun_ids) - 10} more)"
            md_lines.append(f"Unrun item IDs: {sample_unrun}\n")

    md_lines.extend([
        "## Agent Performance KPIs",
        "",
        build_kpi_table_md(metrics),
        "",
        "## Retrieval Benchmark (Offline)",
        "",
        f"Synthetic index of {retrieval_summary['total_components']} components across 64 queries (English, Hindi, Kannada with lexicon normalization):",
        "",
        format_table(retrieval_summary),
        "",
    ])

    failed_items = metrics.get("failed_items", [])
    md_lines.extend([
        "## Failed Items Analysis",
        "",
    ])
    if failed_items:
        md_lines.append(f"Total failed items: {len(failed_items)}\n")
        md_lines.append("| ID | Group | Lang | Split | Message | Failure Reason |")
        md_lines.append("| :--- | :---: | :---: | :---: | :--- | :--- |")
        for f in failed_items:
            clean_msg = str(f.get("message", "")).replace("|", "\\|")
            clean_reason = str(f.get("reason", "")).replace("|", "\\|")
            md_lines.append(
                f"| `{f['id']}` | {f.get('group')} | {f.get('language')} | {f.get('split')} | {clean_msg} | {clean_reason} |"
            )
        md_lines.append("")
    elif n_run > 0:
        md_lines.append("No failures detected among evaluated items. All evaluated requests succeeded.\n")
    else:
        md_lines.append("No items evaluated yet.\n")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    report_json_data = {
        "date": now_str,
        "test_set_size": total_testset_size,
        "items_run": n_run,
        "measured_line": f"Measured on {n_run} requests; targets are not results",
        "unrun_count": len(unrun_ids),
        "unrun_ids": unrun_ids,
        "kpi_metrics": metrics,
        "retrieval_benchmark": retrieval_summary,
        "failed_items": failed_items,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report_json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Report written to:\n  - Markdown: {out_md}\n  - JSON: {out_json}")
    return report_json_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate eval results report in Markdown and JSON.")
    parser.add_argument("--run", type=Path, default=None, help="Path to run JSONL file (defaults to latest)")
    parser.add_argument("--testset", type=Path, default=ROOT / "eval" / "testset.json", help="Path to testset JSON")
    parser.add_argument("--output-md", type=Path, default=ROOT / "eval" / "results.md", help="Path to output results.md")
    parser.add_argument("--output-json", type=Path, default=ROOT / "eval" / "results.json", help="Path to output results.json")

    args = parser.parse_args()
    run_file = args.run
    if run_file is None:
        run_file = find_latest_run(ROOT / "eval" / "runs")

    generate_report(
        run_file=run_file,
        testset_file=args.testset,
        out_md=args.output_md,
        out_json=args.output_json,
    )


if __name__ == "__main__":
    main()
