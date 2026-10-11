# Cognito Pilot Evaluation & Benchmark Harness

This directory contains the evaluation test set, evaluation runner, metrics computation, retrieval benchmarking, and report generation tools for Cognito Pilot.

## Exact Commands to Run (In Order)

### 1. Run Offline Verification Tests (No Gemini calls)
Run the unit and integration tests for the evaluation harness:
```powershell
backend\venv\Scripts\python backend\scripts\test_eval.py
```

### 2. Run Retrieval Benchmark (No Gemini calls)
Benchmark BM25 (keyword), FAISS (semantic), and Hybrid (RRF) on 320 synthetic components across 64 queries (English, Hindi, Kannada):
```powershell
backend\venv\Scripts\python eval\retrieval_bench.py
```

### 3. Run Agent Evaluation (Live Gemini run - performed by user)
Execute the in-process runner against the test set with free-tier rate-limit safety (6s delay, LLM cache, automatic backoff retry, immediate JSONL persistence):
```powershell
# Run dev split (55 requests)
backend\venv\Scripts\python eval\run_eval.py --split dev --name dev_run

# Or run full evaluation (all 70 requests)
backend\venv\Scripts\python eval\run_eval.py --split all --name full_run

# Resume an interrupted run without repeating completed items:
backend\venv\Scripts\python eval\run_eval.py --split dev --name dev_run --resume
```

### 4. Generate Performance Report
Compile KPI metrics and retrieval benchmarks into `eval/results.md` and `eval/results.json`:
```powershell
backend\venv\Scripts\python eval\report.py
```

### 5. Optional: Import Questions from CSV
Validate and convert external user questions from CSV into `testset.json` format:
```powershell
backend\venv\Scripts\python eval\import_questions.py --csv eval/friend_questions.csv
```
