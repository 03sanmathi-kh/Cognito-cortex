# Cognito Pilot Evaluation & Benchmark Results

- **Date**: 2026-10-11 00:05:54
- **Test Set Size**: 70 requests (60 sales, 10 clinic)
- **Items Evaluated**: 10 requests

**Measured on 10 requests; targets are not results.**

> [!NOTE]
> **Partial Run Notice**: 10 of 70 requests have been evaluated. 60 requests were not run.

Unrun item IDs: sales-004, sales-008, sales-010, sales-013, sales-015, sales-016, sales-017, sales-018, sales-019, sales-020, ... (50 more)

## Agent Performance KPIs

| Subset | Count | Task Success | Routing Acc | UI-State Acc | Faithfulness | Abstention | Clarify | Avg Steps | Latency p50 | Latency p95 | Hallucinations |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Overall** | 10 | 100.0% | 100.0% | 100.0% | 60.0% | 100.0% | 100.0% | 2.4 | 7884ms | 25587ms | 8 |
| Split: dev | 10 | 100.0% | 100.0% | 100.0% | 60.0% | 100.0% | 100.0% | 2.4 | 7884ms | 25587ms | 8 |
| Split: heldout | 0 | - | - | - | - | - | - | - | - | - | 0 |
| Language: English | 8 | 100.0% | 100.0% | 100.0% | 75.0% | 100.0% | 100.0% | 2.5 | 7884ms | 26304ms | 6 |
| Language: Hindi | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 2.0 | 3825ms | 3825ms | 1 |
| Language: Kannada | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 2.0 | 21417ms | 21417ms | 1 |

## Retrieval Benchmark (Offline)

Synthetic index of 320 components across 64 queries (English, Hindi, Kannada with lexicon normalization):

| Method | Precision@1 | Precision@5 | Recall@5 | Recall@10 | MRR | Index Time (s) | Query Latency (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| BM25 (Keyword) | 0.672 | 0.138 | 0.688 | 0.688 | 0.682 | 0.006s | 0.6ms |
| FAISS (Semantic) | 0.703 | 0.147 | 0.734 | 0.734 | 0.712 | 7.934s | 8.7ms |
| Hybrid (RRF) | 0.703 | 0.141 | 0.703 | 0.703 | 0.707 | 7.941s | 8.9ms |

## Failed Items Analysis

No failures detected among evaluated items. All evaluated requests succeeded.
