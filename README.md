# Cognito Cortex 🧠

**A context-aware AI assistant embedded in a no-code business application for Meridian Distribution.**

Cognito Cortex enables users to interact with business data through natural language, helping simplify business queries, data analysis, and decision-making.

## 🚀 Key Features

- **Natural-Language Interaction:** Ask business questions in plain English.
- **Agentic AI Workflow:** Interpret requests, plan actions, and execute supported operations.
- **Context-Aware Assistance:** Use business context to generate relevant responses.
- **Hybrid Retrieval:** Combine semantic search and keyword retrieval for relevant information.
- **Business Data Analysis:** Query and analyze structured business data.
- **Validated Execution:** Keep action execution controlled by backend logic.
- **Evidence-Backed Insights:** Ground responses in available business data.

## 🏗️ Architecture

```text
User
  |
React + Vite Frontend
  |
FastAPI Backend
  |
AI Agent Orchestration
  |
  +-- Gemini LLM
  +-- Action Planning and Validation
  +-- Business Data Analysis
  +-- Hybrid Information Retrieval
       |
       +-- FAISS Semantic Search
       +-- BM25 Keyword Search
  |
DuckDB Business Database
  |
Business Insights and Responses
```

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI, Uvicorn |
| AI | Google Gemini API |
| Database | DuckDB |
| Retrieval | FAISS, BM25 |

## 📁 Project Structure

```text
Cognito-Cortex/
├── .env.example
├── README.md
├── PROJECT_SPEC.md
├── PROGRESS.md
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── scripts/
│       └── bootstrap_data.py
├── data/
├── eval/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── index.css
        └── main.tsx
```

## ⚙️ Setup and Installation

### Prerequisites

- Python compatible with the backend dependencies
- Node.js and npm
- Google AI Studio API key

### 1. Configure environment variables

Copy `.env.example` to `.env` in the project root and configure:

```env
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=your_configured_model_name
```

Keep your API key private and never commit `.env`.

### 2. Install backend dependencies

```bash
cd backend
python -m venv venv
```

Activate the environment:

**Linux/macOS**
```bash
source venv/bin/activate
```

**Windows**
```powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies and initialize the data:

```bash
pip install -r requirements.txt
python scripts/bootstrap_data.py
```

### 3. Start the backend

From the `backend` directory:

```bash
uvicorn main:app --reload --port 8000
```

Health check: http://localhost:8000/health

Expected response:

```json
{"status":"ok"}
```

### 4. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## 🔒 Security

- Store API keys in backend environment variables.
- Never expose secrets in frontend code or commit them to Git.
- Validate AI-generated actions before execution.
- Keep generated databases and retrieval caches out of version control.

## 🎯 Vision

Cognito Cortex bridges natural-language interaction and business intelligence, helping users access business information and derive actionable insights through an intuitive conversational interface.

**Cognito Cortex — Ask naturally. Analyze intelligently. Act confidently.**
