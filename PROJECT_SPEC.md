# Cognito Cortex - Project Specification

Product: a context-aware AI assistant embedded in a no-code business app. The user types a natural-language request; Cognito Pilot understands intent, operates the app (navigates to the right page, sets filters, date ranges and sorting), retrieves and analyzes data (trends, period comparisons, likely causes), and presents answers with charts, summary cards and a clear explanation of the actions taken. It must never invent pages, filters or values.

Demo tenant: "Meridian Distribution", a multi-region distribution company (North, South, East, West) with sales, finance, operations, customers and inventory. The engine is generic: it reads any app's metadata JSON.

Signature features: (1) Receipts: every number is clickable and shows the page, filters, date range and SQL behind it. (2) Plan preview, ghost cursor and one-click Undo. (3) Screen-aware context via a ui_context object on every message. (4) All math is computed by code, the LLM only explains; seasonality-aware. (5) "Did you mean…?" validation against metadata, never made-up actions. (6) Role-aware access. (7) Teach-once shortcuts. (8) Proactive insight chips. (9) Plug-in importer for any app's metadata. (10) Live evaluation scoreboard page.

Stack: Frontend: Vite + React + TypeScript, Tailwind CSS, shadcn/ui, Framer Motion, Recharts, Zustand, React Router, lucide-react. Backend: FastAPI with SSE streaming, DuckDB, FAISS + sentence-transformers + BM25, NetworkX, Gemini REST API tool calling with a hand-written loop (no LangChain).

Rules: Keep it simple and runnable with one command per server. Reuse existing components and design tokens. Only change what the current step needs. Secrets go in .env.
