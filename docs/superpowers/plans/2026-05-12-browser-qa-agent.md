# Browser QA Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web dashboard that starts and visualizes LangGraph-powered browser QA runs.

**Architecture:** A FastAPI backend owns run orchestration, LangGraph state transitions, Playwright browser execution, DeepSeek planning/judging calls, and local run storage. A Vite React frontend starts runs, polls status, renders graph nodes, screenshots, issues, logs, and the Markdown report.

**Tech Stack:** Python, FastAPI, LangGraph, Playwright, OpenAI-compatible DeepSeek client, pytest, React, TypeScript, Vite, Tailwind CSS.

---

### Task 1: Backend Core Models and Storage

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/services/run_store.py`
- Test: `backend/tests/test_run_store.py`

- [x] **Step 1: Write failing tests for run storage**

Tests cover creating a run, appending events, updating fields, saving reports, and listing runs.

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_run_store.py -v`

- [x] **Step 3: Implement minimal storage**

Use JSON files under `runs/<run_id>/state.json` and `report.md`.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_run_store.py -v`

### Task 2: LLM Planning Client

**Files:**
- Create: `backend/app/services/llm.py`
- Test: `backend/tests/test_llm.py`

- [x] **Step 1: Write failing tests for robust JSON parsing and fallback plans**

Tests cover fenced JSON, plain JSON, malformed model output, and no-key fallback behavior.

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_llm.py -v`

- [x] **Step 3: Implement DeepSeek client wrapper**

Default to `deepseek-v4-pro`, `https://api.deepseek.com`, and environment variables.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_llm.py -v`

### Task 3: Browser and LangGraph Workflow

**Files:**
- Create: `backend/app/services/browser.py`
- Create: `backend/app/graph/state.py`
- Create: `backend/app/graph/nodes.py`
- Create: `backend/app/graph/workflow.py`
- Test: `backend/tests/test_workflow_helpers.py`

- [x] **Step 1: Write failing tests for issue heuristics and report rendering**

Tests cover console/network errors becoming issues and Markdown report content.

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_workflow_helpers.py -v`

- [x] **Step 3: Implement browser service and LangGraph nodes**

Use Playwright for page inspection/execution and LangGraph conditional retry flow.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_workflow_helpers.py -v`

### Task 4: FastAPI Application

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`

- [x] **Step 1: Add app endpoints**

Endpoints: create run, get run, list runs, get report, serve screenshots.

- [x] **Step 2: Verify import and route registration**

Run: `python -m pytest backend/tests -v`

### Task 5: React Dashboard

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/components/*.tsx`
- Create: `frontend/src/styles.css`

- [x] **Step 1: Build a dashboard shell**

Include URL input, run button, graph timeline, issue panel, screenshot panel, log panel, and report panel.

- [x] **Step 2: Wire polling to backend API**

Poll `/api/runs/:id` every two seconds until terminal status.

- [x] **Step 3: Verify TypeScript build**

Run: `npm run build`

### Task 6: Documentation and Verification

**Files:**
- Create: `README.md`
- Create: `.gitignore`

- [x] **Step 1: Document setup and usage**

Include backend install, Playwright install, frontend install, `.env`, and startup commands.

- [x] **Step 2: Run final checks**

Run backend tests, frontend build, and import smoke checks.
