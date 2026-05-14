from __future__ import annotations

import asyncio
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.graph.workflow import build_workflow
from app.models import CreateRunRequest
from app.services.browser import BrowserService
from app.services.llm import LLMClient
from app.services.run_store import RunStore


settings = get_settings()
store = RunStore(settings.runs_dir)
browser = BrowserService(store)
llm = LLMClient(
    api_key=settings.deepseek_api_key,
    model=settings.deepseek_model,
    base_url=settings.deepseek_base_url,
)

app = FastAPI(title="Browser QA Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/runs", StaticFiles(directory=settings.runs_dir), name="runs")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs")
async def create_run(request: CreateRunRequest) -> dict:
    run = store.create_run(str(request.url))
    asyncio.create_task(execute_run(run["id"], run["url"]))
    return run


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return store.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return store.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str) -> str:
    try:
        run = store.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    report_path = run.get("report_path")
    if not report_path:
        raise HTTPException(status_code=404, detail="Report not ready")
    return Path(report_path).read_text(encoding="utf-8")


async def execute_run(run_id: str, url: str) -> None:
    workflow = build_workflow()
    try:
        store.update_run(run_id, status="running", current_node="starting")
        store.append_event(run_id, "starting", "LangGraph workflow started")
        await workflow.ainvoke(
            {
                "run_id": run_id,
                "url": url,
                "retry_count": 0,
                "run_store": store,
                "browser": browser,
                "llm": llm,
            }
        )
    except Exception as exc:
        error = str(exc) or repr(exc)
        store.save_json(run_id, "traceback.json", {"traceback": traceback.format_exc()})
        store.append_event(run_id, "failed", error)
        store.update_run(run_id, status="failed", current_node="failed", error=error)
