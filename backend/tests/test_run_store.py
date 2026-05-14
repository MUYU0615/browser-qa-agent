from pathlib import Path

from app.services.run_store import RunStore


def test_create_run_persists_initial_state(tmp_path: Path) -> None:
    store = RunStore(tmp_path)

    run = store.create_run("https://example.com")

    assert run["url"] == "https://example.com"
    assert run["status"] == "queued"
    assert run["current_node"] == "queued"
    assert run["events"][0]["message"] == "Run created"
    assert run["llm_calls"] == []
    assert (tmp_path / run["id"] / "state.json").exists()


def test_update_run_appends_events_and_report(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run = store.create_run("https://example.com")

    store.update_run(run["id"], status="running", current_node="page_analyzer")
    store.append_event(run["id"], "page_analyzer", "Page analyzed")
    report_path = store.save_report(run["id"], "# QA Report")

    loaded = store.get_run(run["id"])
    assert loaded["status"] == "running"
    assert loaded["current_node"] == "page_analyzer"
    assert loaded["events"][-1]["message"] == "Page analyzed"
    assert loaded["report_path"] == str(report_path)
    assert report_path.read_text(encoding="utf-8") == "# QA Report"


def test_list_runs_returns_newest_first(tmp_path: Path) -> None:
    store = RunStore(tmp_path)

    first = store.create_run("https://first.example")
    second = store.create_run("https://second.example")

    runs = store.list_runs()
    assert [run["id"] for run in runs] == [second["id"], first["id"]]


def test_append_llm_call_persists_trace(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run = store.create_run("https://example.com")

    store.append_llm_call(
        run["id"],
        {
            "node": "test_planner",
            "purpose": "plan_steps",
            "called_model": True,
            "model": "deepseek-v4-pro",
            "prompt": "Return test steps",
            "raw_output": "[{}]",
            "parsed_output": [{}],
        },
    )

    loaded = store.get_run(run["id"])
    assert len(loaded["llm_calls"]) == 1
    assert loaded["llm_calls"][0]["purpose"] == "plan_steps"
    assert loaded["llm_calls"][0]["called_model"] is True
    assert "at" in loaded["llm_calls"][0]
