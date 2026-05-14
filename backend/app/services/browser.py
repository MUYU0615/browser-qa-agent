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
  return Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[role="link"],[tabindex]'))
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
    const role = el.getAttribute('role') || '';
    const type = el.getAttribute('type') || '';
    return {
      kind: tag === 'a' ? 'link' : role || tag,
      text,
      label,
      placeholder,
      type,
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

    async def execute_component_coverage(
        self,
        url: str,
        run_id: str,
        max_components: int = 25,
        dynamic_depth: int = 1,
        scenarios: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._execute_component_coverage_sync,
            url,
            run_id,
            max_components,
            dynamic_depth,
            scenarios,
        )

    def _execute_component_coverage_sync(
        self,
        url: str,
        run_id: str,
        max_components: int,
        dynamic_depth: int,
        scenarios: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        all_console_errors: list[dict[str, Any]] = []
        all_network_errors: list[dict[str, Any]] = []
        all_execution_results: list[dict[str, Any]] = []
        all_screenshots: list[str] = []
        all_steps: list[dict[str, Any]] = []
        attempts: list[dict[str, Any]] = []
        last_page: dict[str, Any] = {"title": "", "elements": []}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            inventory_page = browser.new_page(viewport={"width": 1440, "height": 1000})
            inventory_page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            self._wait_for_network_idle(inventory_page)
            initial_page = self._page_summary_sync(inventory_page)
            inventory_page.close()

            planned_scenarios = scenarios or component_scenarios_from_page(initial_page, max_components)
            tested_keys = {
                key
                for scenario in planned_scenarios
                for key in scenario_component_keys(scenario)
            }
            for element in initial_page.get("elements", []):
                if should_test_component(element):
                    tested_keys.update(component_identity_keys(element))
            attempt_number = 0
            while planned_scenarios and attempt_number < max_components:
                scenario = planned_scenarios.pop(0)
                attempt_number += 1
                page_console_errors: list[dict[str, Any]] = []
                page_network_errors: list[dict[str, Any]] = []
                branch_steps: list[dict[str, Any]] = [step for step in scenario.get("steps", []) if isinstance(step, dict)]
                branch_results: list[dict[str, Any]] = []
                branch_screenshots: list[str] = []

                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                self._wire_observers(page, page_console_errors, page_network_errors)
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                self._wait_for_network_idle(page)

                for step_number, step in enumerate(branch_steps, start=1):
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

                    shot = self._screenshot_sync(page, run_id, scenario_screenshot_filename(attempt_number, step_number))
                    result = {
                        **step,
                        "ok": ok,
                        "error": error,
                        "screenshot": shot,
                        "scenario": scenario.get("name", f"Scenario {attempt_number}"),
                        "page_url": page.url,
                    }
                    branch_results.append(result)
                    branch_screenshots.append(shot)

                    if not ok:
                        break
                    last_page = self._page_summary_sync(page)
                    if same_page(url, last_page.get("url", "")):
                        new_scenarios = component_scenarios_from_page(
                            last_page,
                            max_components=max_components,
                            seen_keys=tested_keys,
                        )
                        for new_scenario in new_scenarios:
                            tested_keys.update(scenario_component_keys(new_scenario))
                            branch_steps.extend(new_scenario.get("steps", []))

                page.close()
                all_console_errors.extend(page_console_errors)
                all_network_errors.extend(page_network_errors)
                all_execution_results.extend(branch_results)
                all_screenshots.extend(branch_screenshots)
                all_steps.extend(branch_steps)
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "phase": "scenario",
                        "target": scenario.get("name", f"Scenario {attempt_number}"),
                        "test_steps": branch_steps,
                        "execution_results": branch_results,
                        "console_errors": page_console_errors,
                        "network_errors": page_network_errors,
                        "screenshots": branch_screenshots,
                    }
                )

            browser.close()

        return {
            "title": last_page.get("title") or initial_page.get("title", ""),
            "elements": initial_page.get("elements", []),
            "test_steps": all_steps,
            "execution_results": all_execution_results,
            "console_errors": all_console_errors,
            "network_errors": all_network_errors,
            "screenshots": all_screenshots,
            "attempts": attempts,
        }

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
        elif action == "check":
            if not selector:
                raise ValueError("Check step is missing selector")
            page.locator(selector).first.check(timeout=5_000)
        elif action == "select":
            if not selector:
                raise ValueError("Select step is missing selector")
            page.locator(selector).first.select_option(index=1, timeout=5_000)
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


def component_screenshot_filename(attempt_number: int, step_number: int) -> str:
    return f"component-{attempt_number}-step-{step_number}.png"


def scenario_screenshot_filename(attempt_number: int, step_number: int) -> str:
    return f"scenario-{attempt_number}-step-{step_number}.png"


def component_scenarios_from_page(
    page: dict[str, Any],
    max_components: int = 25,
    seen_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    seen = seen_keys or set()
    targets = [
        element
        for element in page.get("elements", [])
        if should_test_component(element)
        and component_key(element) not in seen
        and element.get("selector") not in seen
        and not component_identity_keys(element).intersection(seen)
    ]
    scenarios: list[dict[str, Any]] = []
    pending_fields: list[dict[str, Any]] = []
    covered = 0

    def add_scenario(name: str, components: list[dict[str, Any]]) -> None:
        nonlocal covered
        if covered >= max_components:
            return
        selected = components[: max_components - covered]
        steps = [component_test_step(component) for component in selected]
        selectors = [component.get("selector") for component in selected if component.get("selector")]
        if steps:
            scenarios.append({"name": name, "target_components": selectors, "steps": steps})
            covered += len(selected)

    for target in targets:
        kind = target.get("kind")
        if kind in {"input", "textarea", "select"}:
            pending_fields.append(target)
            continue
        if kind in {"button", "link"}:
            if pending_fields:
                components = [*pending_fields, target]
                add_scenario(scenario_label(components), components)
                pending_fields = []
            else:
                add_scenario(scenario_label([target]), [target])

    if pending_fields:
        add_scenario(scenario_label(pending_fields), pending_fields)

    return scenarios


def component_key(component: dict[str, Any]) -> str:
    return f"{component.get('kind', 'unknown')}:{component.get('selector') or component.get('text') or component.get('label')}"


def component_identity_keys(component: dict[str, Any]) -> set[str]:
    kind = str(component.get("kind", "unknown"))
    keys = {component_key(component)}
    selector = component.get("selector")
    text = component.get("text")
    label = component.get("label")
    placeholder = component.get("placeholder")
    if selector:
        keys.add(str(selector))
    if text:
        keys.add(f"{kind}:text:{text}")
    if label:
        keys.add(f"{kind}:label:{label}")
    if placeholder:
        keys.add(f"{kind}:placeholder:{placeholder}")
    return keys


def component_label(component: dict[str, Any]) -> str:
    return str(component.get("text") or component.get("label") or component.get("placeholder") or component.get("selector") or "component")


def scenario_label(components: list[dict[str, Any]]) -> str:
    labels = [component_label(component) for component in components]
    text = " ".join(labels).lower()
    if "login" in text or ("password" in text and ("user" in text or "email" in text)):
        return "登录流程"
    if "search" in text:
        return "搜索流程"
    if len(components) > 1:
        return f"表单流程：{labels[-1]}"
    return f"组件流程：{labels[0]}"


def should_test_component(component: dict[str, Any]) -> bool:
    if component.get("disabled"):
        return False
    if not component.get("selector"):
        return False
    return component.get("kind") in {"link", "button", "input", "textarea", "select"}


def component_test_step(component: dict[str, Any]) -> dict[str, Any]:
    kind = component.get("kind")
    selector = component.get("selector")
    label = component_label(component)
    if kind in {"button", "link"}:
        return {"description": f"测试组件：点击 {label}", "action": "click", "selector": selector}
    if kind == "select":
        return {"description": f"测试组件：选择 {label}", "action": "select", "selector": selector}
    if kind == "input" and str(component.get("type", "")).lower() in {"checkbox", "radio"}:
        return {"description": f"测试组件：切换 {label}", "action": "check", "selector": selector}
    if kind in {"input", "textarea"}:
        return {"description": f"测试组件：填写 {label}", "action": "fill", "selector": selector, "value": "qa@example.com"}
    return {"description": f"测试组件：点击 {label}", "action": "click", "selector": selector}


def scenario_component_keys(scenario: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for step in scenario.get("steps", []):
        if not isinstance(step, dict):
            continue
        selector = step.get("selector")
        action = step.get("action")
        if selector and action in {"click", "fill", "check", "select"}:
            kind = "button" if action == "click" else "input"
            keys.add(str(selector))
            keys.add(f"{kind}:{selector}")
    return keys


def same_page(original_url: str, current_url: str) -> bool:
    return current_url.split("#", 1)[0] == original_url.split("#", 1)[0]


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
