from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RunStore:
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_run(self, url: str) -> dict[str, Any]:
        run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f") + "-" + uuid.uuid4().hex[:8]
        now = utc_now()
        run = {
            "id": run_id,
            "url": url,
            "status": "queued",
            "current_node": "queued",
            "created_at": now,
            "updated_at": now,
            "events": [{"at": now, "node": "queued", "message": "Run created"}],
            "llm_calls": [],
            "attempts": [],
            "screenshots": [],
            "issues": [],
            "report_path": None,
            "error": None,
        }
        self._write(run_id, run)
        return run

    def list_runs(self) -> list[dict[str, Any]]:
        runs = []
        for state_file in self.base_dir.glob("*/state.json"):
            try:
                runs.append(json.loads(state_file.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return sorted(runs, key=lambda item: item["created_at"], reverse=True)

    def get_run(self, run_id: str) -> dict[str, Any]:
        path = self._state_path(run_id)
        if not path.exists():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def update_run(self, run_id: str, **changes: Any) -> dict[str, Any]:
        run = self.get_run(run_id)
        run.update(changes)
        run["updated_at"] = utc_now()
        self._write(run_id, run)
        return run

    def append_event(self, run_id: str, node: str, message: str, **extra: Any) -> dict[str, Any]:
        run = self.get_run(run_id)
        event = {"at": utc_now(), "node": node, "message": message}
        event.update(extra)
        run.setdefault("events", []).append(event)
        run["updated_at"] = utc_now()
        self._write(run_id, run)
        return event

    def append_llm_call(self, run_id: str, trace: dict[str, Any]) -> dict[str, Any]:
        run = self.get_run(run_id)
        entry = {"at": utc_now(), **trace}
        run.setdefault("llm_calls", []).append(entry)
        run["updated_at"] = utc_now()
        self._write(run_id, run)
        return entry

    def save_report(self, run_id: str, content: str) -> Path:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "report.md"
        report_path.write_text(content, encoding="utf-8")
        self.update_run(run_id, report_path=str(report_path))
        return report_path

    def save_json(self, run_id: str, filename: str, data: Any) -> Path:
        path = self._run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def run_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id)

    def _write(self, run_id: str, run: dict[str, Any]) -> None:
        path = self._state_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")

    def _run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id

    def _state_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "state.json"
