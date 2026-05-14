from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env_key = key.strip().lstrip("\ufeff")
        env_value = value.strip().strip('"').strip("'")
        if not os.environ.get(env_key):
            os.environ[env_key] = env_value


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    runs_dir: Path
    playwright_browsers_path: Path
    cors_origins: list[str]


def configure_playwright_browsers_path(root: Path) -> Path:
    configured = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            normalized = path.as_posix()
            if normalized in {".playwright-browsers", "./.playwright-browsers"}:
                path = root / "backend" / ".playwright-browsers"
            else:
                path = root / path
    else:
        path = root / "backend" / ".playwright-browsers"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path)
    return path


def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / "backend" / ".env")
    load_dotenv(root / ".env")
    playwright_browsers_path = configure_playwright_browsers_path(root)
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        runs_dir=Path(os.getenv("RUNS_DIR", "runs")),
        playwright_browsers_path=playwright_browsers_path,
        cors_origins=[
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ],
    )
