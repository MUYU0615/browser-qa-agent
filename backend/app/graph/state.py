from __future__ import annotations

from typing import Any, TypedDict


class QAState(TypedDict, total=False):
    run_id: str
    url: str
    title: str
    elements: list[dict[str, Any]]
    test_steps: list[dict[str, Any]]
    planned_steps: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    console_errors: list[dict[str, Any]]
    network_errors: list[dict[str, Any]]
    screenshots: list[str]
    issues: list[dict[str, Any]]
    retry_count: int
    max_steps: int
    max_components: int
    report: str
    error: str
    run_store: Any
    browser: Any
    llm: Any
