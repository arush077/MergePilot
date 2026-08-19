# MergePilot

**MergePilot** is a multi-agent AI system that autonomously converts a GitHub issue into a fully-formed pull request. Feed it an issue URL and a GitHub token — it researches the codebase, drafts a fix, writes tests (when needed), and opens a PR, all without human intervention.

## Demo

![MergePilot UI](frontend/public/5.jpg)

## How It Works

MergePilot runs a 5-agent pipeline, each step routing based on the current state:

| Step | Agent | Action |
|---|---|---|
| 1 | **Issue Analyzer** | Classifies issue type (bug/feature/refactor/docs), extracts complexity, affected areas, and suggested files |
| 2 | **Codebase Researcher** | Fetches relevant files from GitHub, chunks them per-file, filters for relevance via LLM |
| 3 | **Fix Drafter** | Produces surgical find/replace edits, validates Python snippets with `compile()` |
| 4 | **Test Writer** | Generates test code (only if the issue explicitly asks for tests) |
| 5 | **PR Creator** | Creates a branch, commits changes, generates a PR description, opens the PR with labels |

A final **review** step sanity-checks the PR before marking the pipeline as done.

## Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | Groq API (`openai/gpt-oss-120b`) |
| **Backend** | Python 3.10+, FastAPI, Uvicorn |
| **Frontend** | React 18, Vite 5, Tailwind CSS 3 |
| **Real-time** | Server-Sent Events (SSE) |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- A [Groq API key](https://console.groq.com/keys)
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (classic or fine-grained with `repo` scope)

### Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd MergePilot

# 2. Create .env file
cp .env.example .env   # or create manually:
                       # GROQ_API_KEY="your_groq_key"
                       # GITHUB_TOKEN="your_github_pat"  (optional, for CLI only)

# 3. Install backend
pip install -e .
pip install -r backend/requirements.txt

# 4. Install frontend
cd frontend && npm install
```

### Running

**CLI mode:**
```bash
python -m mergepilot https://github.com/owner/repo/issues/42
```

**Web UI (two terminals):**
```bash
# Terminal 1 — backend
python backend/main.py

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open `http://localhost:5173`, enter your GitHub PAT and issue URL, and click **Run**.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/run` | Start a pipeline run (body: `{issue_url, github_token}`) |
| `GET` | `/stream/{run_id}` | SSE stream of pipeline progress events |

## Project Structure

```
MergePilot/
├── backend/               # FastAPI server
│   ├── main.py            # API routes
│   └── requirements.txt
├── frontend/              # React + Vite UI
│   ├── src/
│   │   ├── App.jsx        # Main UI component
│   │   └── main.jsx       # Entry point
│   └── package.json
├── mergepilot/            # Core library
│   ├── agents.py          # 5 agent implementations
│   ├── orchestrator.py    # Pipeline router
│   └── state.py           # Shared AgentState
├── pyproject.toml
└── .env
```

## Key Features

- **Fully autonomous** — from issue URL to a real PR on GitHub, zero human intervention
- **Surgical edits** — only changes the minimum lines needed via find/replace, not whole-file rewrites
- **AST-based chunking** — parses Python files into function/class-level chunks for precise LLM context
- **Conditional test generation** — only writes tests when the issue explicitly asks for them
- **Real-time SSE streaming** — live pipeline visualization with per-agent status and a log viewer
- **Rate-limit resilience** — exponential backoff for GitHub API rate limits (429/403)
- **Graceful degradation** — frontend has a complete mock mode that works offline
- **No token persistence** — GitHub PAT is used in-memory per run, never stored

## License

MIT
