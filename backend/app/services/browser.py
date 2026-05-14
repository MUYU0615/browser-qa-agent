from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.services.run_store import RunStore


PAGE_SUMMARY_SCRIPT = """
() => {
  function cssPath(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const testId = el.getAttribute('data-testid');
    if (testId) return `[data-testid="${testId}"]`;
    const parts = [];
    let cursor = el;
    while (cursor && cursor.nodeType === Node.ELEMENT_NODE && cursor !== document.body && parts.length < 5) {
      let tag = cursor.tagName.toLowerCase();
      const parent = cursor.parentElement;
      if (parent) {
        const sameTag = Array.from(parent.children).filter(child => child.tagName === cursor.tagName);
        if (sameTag.length > 1) tag += `:nth-of-type(${sameTag.indexOf(cursor) + 1})`;
      }
      parts.unshift(tag);
      cursor = parent;
    }
    return parts.join(' > ');
  }
  return Array.from(document.querySelectorAll('a,button,input,textarea,select'))
  .filter((el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  })
  .slice(0, 40)
  .map((el) => {
    const tag = el.tagName.toLowerCase();
    const text = (el.innerText || el.value || '').trim().slice(0, 80);
    const label = el.getAttribute('aria-label') || el.getAttribute('name') || '';
    const placeholder = el.getAttribute('placeholder') || '';
    return {
      kind: tag === 'a' ? 'link' : tag,
      text,
      label,
      placeholder,
      selector: cssPath(el),
      disabled: Boolean(el.disabled),
      href: el.href || ''
    };
  })
}
"""


class BrowserService:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    async def inspect_page(self, url: str, run_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._inspect_page_sync, url, run_id)

    async def execute_steps(
        self,
        url: str,
        steps: list[dict[str, Any]],
        run_id: str,
        attempt_number: int = 1,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._execute_steps_sync, url, steps, run_id, attempt_number)

    async def execute_stepwise(
        self,
        url: str,
        run_id: str,
        planner: Callable[[dict[str, Any], list[dict[str, Any]], int, int], Awaitable[dict[str, Any]]],
        max_steps: int = 5,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(self._execute_stepwise_sync, url, run_id, planner, max_steps, loop)

    def _execute_stepwise_sync(
        self,
        url: str,
        run_id: str,
        planner: Callable[[dict[str, Any], list[dict[str, Any]], int, int], Awaitable[dict[str, Any]]],
        max_steps: int,
        loop: asyncio.AbstractEventLoop,
    ) -> dict[str, Any]:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        console_errors: list[dict[str, Any]] = []
        network_errors: list[dict[str, Any]] = []
        execution_results: list[dict[str, Any]] = []
        screenshots: list[str] = []
        test_steps: list[dict[str, Any]] = []
        last_page: dict[str, Any] = {"title": "", "elements": []}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            self._wire_observers(page, console_errors, network_errors)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            self._wait_for_network_idle(page)

            for step_number in range(1, max_steps + 1):
                last_page = self._page_summary_sync(page)
                trace = run_planner_sync(planner, last_page, execution_results, step_number, max_steps, loop)
                plan = trace.get("parsed_output", {})
                if plan.get("should_stop"):
                    break
                step = plan.get("step")
                if not isinstance(step, dict):
                    break
                test_steps.append(step)
                description = step.get("description", step.get("action", f"Step {step_number}"))
                try:
                    self._execute_step_sync(page, step)
                    ok = True
                    error = None
                except PlaywrightTimeoutError as exc:
                    ok = False
                    error = f"Timeout while running step: {exc}"
                except Exception as exc:
                    ok = False
                    error = str(exc)

                shot = self._screenshot_sync(page, run_id, screenshot_filename(1, step_number))
                screenshots.append(shot)
                result = {
                    **step,
                    "ok": ok,
                    "description": description,
                    "action": step.get("action"),
                    "error": error,
                    "screenshot": shot,
                }
                execution_results.append(result)
                if not ok:
                    break

            last_page = self._page_summary_sync(page)
            browser.close()

        return {
            "title": last_page.get("title", ""),
            "elements": last_page.get("elements", []),
            "test_steps": test_steps,
            "execution_results": execution_results,
            "console_errors": console_errors,
            "network_errors": network_errors,
            "screenshots": screenshots,
        }

    def _inspect_page_sync(self, url: str, run_id: str) -> dict[str, Any]:
        from playwright.sync_api import sync_playwright

        console_errors: list[dict[str, Any]] = []
        network_errors: list[dict[str, Any]] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            self._wire_observers(page, console_errors, network_errors)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            self._wait_for_network_idle(page)
            title = page.title()
            elements = page.evaluate(PAGE_SUMMARY_SCRIPT)
            screenshot = self._screenshot_sync(page, run_id, "initial.png")
            browser.close()

        return {
            "title": title,
            "elements": elements,
            "console_errors": console_errors,
            "network_errors": network_errors,
            "screenshots": [screenshot],
        }

    def _execute_steps_sync(
        self,
        url: str,
        steps: list[dict[str, Any]],
        run_id: str,
        attempt_number: int,
    ) -> dict[str, Any]:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        console_errors: list[dict[str, Any]] = []
        network_errors: list[dict[str, Any]] = []
        execution_results: list[dict[str, Any]] = []
        screenshots: list[str] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            self._wire_observers(page, console_errors, network_errors)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            self._wait_for_network_idle(page)

            for index, step in enumerate(steps, start=1):
                description = step.get("description", step.get("action", f"Step {index}"))
                try:
                    self._execute_step_sync(page, step)
                    ok = True
                    error = None
                except PlaywrightTimeoutError as exc:
                    ok = False
                    error = f"Timeout while running step: {exc}"
                except Exception as exc:
                    ok = False
                    error = str(exc)
                shot = self._screenshot_sync(page, run_id, screenshot_filename(attempt_number, index))
                screenshots.append(shot)
                execution_results.append(
                    {**step, "ok": ok, "description": description, "action": step.get("action"), "error": error, "screenshot": shot}
                )
            browser.close()

        return {
            "execution_results": execution_results,
            "console_errors": console_errors,
            "network_errors": network_errors,
            "screenshots": screenshots,
        }

    def _execute_step_sync(self, page: Any, step: dict[str, Any]) -> None:
        action = step.get("action")
        selector = step.get("selector")
        if action == "assert_title":
            title = page.title()
            if not title:
                raise AssertionError("Page title is empty")
        elif action == "assert_text":
            text = step.get("text")
            if text:
                page.get_by_text(text, exact=False).first.wait_for(timeout=5_000)
        elif action == "fill":
            if not selector:
                raise ValueError("Fill step is missing selector")
            page.locator(selector).first.fill(str(step.get("value", "qa@example.com")), timeout=5_000)
        elif action == "click":
            if not selector:
                raise ValueError("Click step is missing selector")
            page.locator(selector).first.click(timeout=5_000)
            self._wait_for_domcontentloaded(page)
        else:
            raise ValueError(f"Unsupported action: {action}")

    async def _execute_step_async(self, page: Any, step: dict[str, Any]) -> None:
        action = step.get("action")
        selector = step.get("selector")
        if action == "assert_title":
            title = await page.title()
            if not title:
                raise AssertionError("Page title is empty")
        elif action == "assert_text":
            text = step.get("text")
            if text:
                await page.get_by_text(text, exact=False).first.wait_for(timeout=5_000)
        elif action == "fill":
            if not selector:
                raise ValueError("Fill step is missing selector")
            await page.locator(selector).first.fill(str(step.get("value", "qa@example.com")), timeout=5_000)
        elif action == "click":
            if not selector:
                raise ValueError("Click step is missing selector")
            await page.locator(selector).first.click(timeout=5_000)
            await self._wait_for_domcontentloaded_async(page)
        else:
            raise ValueError(f"Unsupported action: {action}")

    def _wire_observers(self, page: Any, console_errors: list[dict[str, Any]], network_errors: list[dict[str, Any]]) -> None:
        page.on(
            "console",
            lambda msg: console_errors.append({"type": msg.type, "text": msg.text}) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: console_errors.append({"type": "pageerror", "text": str(exc)}))
        page.on(
            "response",
            lambda response: network_errors.append({"url": response.url, "status": response.status})
            if response.status >= 400
            else None,
        )

    def _screenshot_sync(self, page: Any, run_id: str, filename: str) -> str:
        path = self.store.run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
        return f"/runs/{run_id}/{filename}"

    async def _screenshot_async(self, page: Any, run_id: str, filename: str) -> str:
        path = self.store.run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=True)
        return f"/runs/{run_id}/{filename}"

    async def _page_summary_async(self, page: Any) -> dict[str, Any]:
        return {
            "title": await page.title(),
            "url": page.url,
            "elements": await page.evaluate(PAGE_SUMMARY_SCRIPT),
        }

    def _page_summary_sync(self, page: Any) -> dict[str, Any]:
        return {
            "title": page.title(),
            "url": page.url,
            "elements": page.evaluate(PAGE_SUMMARY_SCRIPT),
        }

    def _wait_for_network_idle(self, page: Any) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)

    def _wait_for_domcontentloaded(self, page: Any) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            return

    async def _wait_for_network_idle_async(self, page: Any) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)

    async def _wait_for_domcontentloaded_async(self, page: Any) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            return


def screenshot_filename(attempt_number: int, step_number: int) -> str:
    return f"attempt-{attempt_number}-step-{step_number}.png"


def run_planner_sync(
    planner: Callable[[dict[str, Any], list[dict[str, Any]], int, int], Awaitable[dict[str, Any]]],
    page: dict[str, Any],
    history: list[dict[str, Any]],
    current_step: int,
    max_steps: int,
    loop: asyncio.AbstractEventLoop,
) -> dict[str, Any]:
    future = asyncio.run_coroutine_threadsafe(planner(page, history, current_step, max_steps), loop)
    return future.result(timeout=120)
