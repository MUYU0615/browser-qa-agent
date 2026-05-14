import os
from pathlib import Path

from app.config import configure_playwright_browsers_path, load_dotenv


def test_configure_playwright_browsers_path_defaults_to_backend_dir(monkeypatch) -> None:
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    root = Path("D:/MUYU/browser-qa-agent")

    path = configure_playwright_browsers_path(root)

    assert path == root / "backend" / ".playwright-browsers"
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(path)


def test_configure_playwright_browsers_path_resolves_relative_to_project_root(monkeypatch) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "backend/.playwright-browsers")
    root = Path("D:/MUYU/browser-qa-agent")

    path = configure_playwright_browsers_path(root)

    assert path == root / "backend" / ".playwright-browsers"
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(path)


def test_configure_playwright_browsers_path_keeps_legacy_dot_path_in_backend(monkeypatch) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "./.playwright-browsers")
    root = Path("D:/MUYU/browser-qa-agent")

    path = configure_playwright_browsers_path(root)

    assert path == root / "backend" / ".playwright-browsers"
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(path)


def test_load_dotenv_overwrites_empty_environment_value(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("\ufeffDEEPSEEK_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")

    load_dotenv(env_file)

    assert os.environ["DEEPSEEK_API_KEY"] == "sk-test-key"
