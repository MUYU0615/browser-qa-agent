from __future__ import annotations

from typing import Any

from app.graph.state import QAState


DANGEROUS_WORDS = {"pay", "payment", "checkout", "purchase", "unsubscribe"}
DANGEROUS_PHRASES = {
    "delete account",
    "remove account",
    "delete user",
    "remove user",
    "delete project",
    "delete repository",
    "delete repo",
    "deactivate account",
    "close account",
    "删除账号",
    "删除账户",
    "注销账号",
    "注销账户",
}
ACTIVE_SCRIPT_MARKERS = {"<script", "</script", "javascript:", "onerror=", "onload=", "alert("}


async def page_analyzer_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    store.update_run(run_id, status="running", current_node="page_analyzer")
    store.append_event(run_id, "page_analyzer", "Inspecting page structure")
    page = await state["browser"].inspect_page(state["url"], run_id)
    store.update_run(run_id, screenshots=page.get("screenshots", []))
    return {**state, **page}


async def test_planner_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    store.update_run(run_id, current_node="test_planner")
    store.append_event(run_id, "test_planner", "Planning browser QA steps")
    page = {"title": state.get("title", ""), "elements": state.get("elements", [])}
    trace = await state["llm"].plan_steps_with_trace(state["url"], page)
    store.append_llm_call(run_id, {"node": "test_planner", **trace})
    store.append_event(
        run_id,
        "test_planner",
        "LLM planner used model" if trace["called_model"] else f"LLM planner fallback: {trace['fallback_reason']}",
    )
    steps = trace["parsed_output"]
    safe_steps = [step for step in steps if not is_dangerous_step(step)]
    store.save_json(run_id, "planned_steps.json", safe_steps)
    return {**state, "test_steps": safe_steps, "planned_steps": safe_steps}


async def browser_executor_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    store.update_run(run_id, current_node="browser_executor")
    store.append_event(run_id, "browser_executor", f"Executing {len(state.get('test_steps', []))} steps")
    attempt_number = state.get("retry_count", 0) + 1
    result = await state["browser"].execute_steps(
        state["url"],
        state.get("test_steps", []),
        run_id,
        attempt_number=attempt_number,
    )
    screenshots = [*state.get("screenshots", []), *result.get("screenshots", [])]
    attempts = [*state.get("attempts", []), build_attempt(state, result)]
    store.update_run(run_id, screenshots=screenshots, attempts=attempts)
    return {
        **state,
        "attempts": attempts,
        "execution_results": result.get("execution_results", []),
        "console_errors": [*state.get("console_errors", []), *result.get("console_errors", [])],
        "network_errors": [*state.get("network_errors", []), *result.get("network_errors", [])],
        "screenshots": screenshots,
    }


async def stepwise_executor_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    max_steps = int(state.get("max_steps", 5))
    store.update_run(run_id, current_node="stepwise_executor")
    store.append_event(run_id, "stepwise_executor", f"Planning and executing up to {max_steps} observed steps")

    async def planner(page: dict[str, Any], history: list[dict[str, Any]], current_step: int, max_steps: int) -> dict[str, Any]:
        store.append_event(
            run_id,
            "stepwise_executor",
            f"Planning step {current_step} from {len(page.get('elements', []))} observed elements",
        )
        trace = await state["llm"].plan_next_step_with_trace(state["url"], page, history, current_step, max_steps)
        plan = trace.get("parsed_output", {})
        step = plan.get("step") if isinstance(plan, dict) else None
        if isinstance(step, dict) and is_dangerous_step(step):
            trace = {
                **trace,
                "parsed_output": {"should_stop": True, "step": None, "reason": "unsafe_step_filtered"},
                "fallback_reason": trace.get("fallback_reason", ""),
            }
            store.append_event(run_id, "stepwise_executor", "Stopped before an unsafe planned step")
        elif isinstance(step, dict) and is_redundant_step(step, history):
            trace = {
                **trace,
                "parsed_output": {"should_stop": True, "step": None, "reason": "redundant_step_filtered"},
                "fallback_reason": trace.get("fallback_reason", ""),
            }
            store.append_event(run_id, "stepwise_executor", "Stopped before repeating an already successful step")
        elif isinstance(step, dict):
            store.append_event(
                run_id,
                "stepwise_executor",
                f"Planned step {current_step}: {step.get('description', step.get('action', 'Step'))}",
            )
        store.append_llm_call(run_id, {"node": "stepwise_executor", **trace})
        return trace

    result = await state["browser"].execute_stepwise(state["url"], run_id, planner, max_steps=max_steps)
    screenshots = [*state.get("screenshots", []), *result.get("screenshots", [])]
    attempts = [*state.get("attempts", []), build_attempt({**state, "test_steps": result.get("test_steps", [])}, result)]
    store.update_run(run_id, screenshots=screenshots, attempts=attempts)
    return {
        **state,
        "title": result.get("title", state.get("title", "")),
        "elements": result.get("elements", state.get("elements", [])),
        "test_steps": result.get("test_steps", []),
        "planned_steps": result.get("test_steps", []),
        "attempts": attempts,
        "execution_results": result.get("execution_results", []),
        "console_errors": [*state.get("console_errors", []), *result.get("console_errors", [])],
        "network_errors": [*state.get("network_errors", []), *result.get("network_errors", [])],
        "screenshots": screenshots,
    }


async def component_coverage_executor_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    max_components = int(state.get("max_components", 25))
    store.update_run(run_id, current_node="component_coverage_executor")
    store.append_event(run_id, "component_coverage_executor", f"Planning scenarios for up to {max_components} interactive components")
    page = {"title": state.get("title", ""), "url": state["url"], "elements": state.get("elements", [])}
    trace = await state["llm"].plan_component_scenarios_with_trace(state["url"], page, max_components=max_components)
    store.append_llm_call(run_id, {"node": "component_coverage_executor", **trace})
    scenarios = sanitize_component_scenarios(trace.get("parsed_output", []))
    if hasattr(store, "save_json"):
        store.save_json(run_id, "component_scenarios.json", scenarios)
    store.append_event(
        run_id,
        "component_coverage_executor",
        f"Executing {len(scenarios)} planned scenarios"
        if trace.get("called_model")
        else f"Executing {len(scenarios)} fallback scenarios: {trace.get('fallback_reason', '')}",
    )
    result = await state["browser"].execute_component_coverage(
        state["url"],
        run_id,
        max_components=max_components,
        scenarios=scenarios,
    )
    screenshots = [*state.get("screenshots", []), *result.get("screenshots", [])]
    attempts = [*state.get("attempts", []), *result.get("attempts", [])]
    store.update_run(run_id, screenshots=screenshots, attempts=attempts)
    return {
        **state,
        "title": result.get("title", state.get("title", "")),
        "elements": result.get("elements", state.get("elements", [])),
        "test_steps": result.get("test_steps", []),
        "planned_steps": result.get("test_steps", []),
        "attempts": attempts,
        "execution_results": result.get("execution_results", []),
        "console_errors": [*state.get("console_errors", []), *result.get("console_errors", [])],
        "network_errors": [*state.get("network_errors", []), *result.get("network_errors", [])],
        "screenshots": screenshots,
    }


async def observation_analyzer_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    store.update_run(run_id, current_node="observation_analyzer")
    store.append_event(run_id, "observation_analyzer", "Analyzing browser observations")
    state = {**state}
    state["issues"] = classify_issues(state)
    return state


async def bug_classifier_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    store.update_run(run_id, current_node="bug_classifier")
    store.append_event(run_id, "bug_classifier", "Classifying possible issues")
    trace = await state["llm"].judge_observations_with_trace(
        {
            "url": state["url"],
            "execution_results": state.get("execution_results", []),
            "console_errors": state.get("console_errors", []),
            "network_errors": state.get("network_errors", []),
        }
    )
    store.append_llm_call(run_id, {"node": "bug_classifier", **trace})
    store.append_event(
        run_id,
        "bug_classifier",
        "LLM judge used model" if trace["called_model"] else f"LLM judge fallback: {trace['fallback_reason']}",
    )
    model_issues = trace["parsed_output"]
    issues = [normalize_issue(issue) for issue in [*state.get("issues", []), *model_issues]]
    store.update_run(run_id, issues=issues)
    return {**state, "issues": issues}


async def retry_planner_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    retry_count = state.get("retry_count", 0) + 1
    store.update_run(run_id, current_node="retry_planner")
    store.append_event(run_id, "retry_planner", "Retrying failed interaction with required setup steps")
    retry_steps = plan_retry_steps(state.get("test_steps", []), state.get("execution_results", []))
    return {**state, "retry_count": retry_count, "test_steps": retry_steps}


async def reporter_node(state: QAState) -> QAState:
    store = state["run_store"]
    run_id = state["run_id"]
    store.update_run(run_id, current_node="reporter")
    report = render_report(state)
    store.save_report(run_id, report)
    store.append_event(run_id, "reporter", "Report generated")
    store.update_run(run_id, status="completed", current_node="completed", issues=state.get("issues", []))
    return {**state, "report": report}


def should_retry(state: QAState) -> str:
    has_failed_interaction = any(not result.get("ok", False) for result in state.get("execution_results", []))
    retry_steps = plan_retry_steps(state.get("test_steps", []), state.get("execution_results", []))
    if has_failed_interaction and retry_steps and state.get("retry_count", 0) < 1:
        return "retry"
    return "report"


def is_dangerous_step(step: dict[str, Any]) -> bool:
    text = " ".join(str(value).lower() for value in step.values())
    return (
        any(word in text for word in DANGEROUS_WORDS)
        or any(phrase in text for phrase in DANGEROUS_PHRASES)
        or any(marker in text for marker in ACTIVE_SCRIPT_MARKERS)
    )


def sanitize_component_scenarios(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe_scenarios: list[dict[str, Any]] = []
    for index, scenario in enumerate(scenarios, start=1):
        if not isinstance(scenario, dict):
            continue
        steps = scenario.get("steps", [])
        if not isinstance(steps, list):
            continue
        safe_steps = [step for step in steps if isinstance(step, dict) and not is_dangerous_step(step)]
        if not safe_steps:
            continue
        safe_scenarios.append(
            {
                "name": str(scenario.get("name") or f"Scenario {index}"),
                "target_components": scenario.get("target_components", []),
                "steps": safe_steps,
            }
        )
    return safe_scenarios


def is_redundant_step(step: dict[str, Any], history: list[dict[str, Any]]) -> bool:
    action = step.get("action")
    selector = step.get("selector")
    text = step.get("text")
    for previous in history:
        if not previous.get("ok", False):
            continue
        if previous.get("action") != action:
            continue
        if selector and previous.get("selector") == selector:
            return True
        if action == "assert_text" and text and previous.get("text") == text:
            return True
    return False


def plan_retry_steps(test_steps: list[dict[str, Any]], execution_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, result in enumerate(execution_results):
        if not result.get("ok", False):
            candidate_steps = test_steps[: index + 1]
            if any(is_dangerous_step(step) for step in candidate_steps):
                return []
            return candidate_steps
    return []


def build_attempt(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    attempt_number = state.get("retry_count", 0) + 1
    return {
        "attempt": attempt_number,
        "phase": "initial" if attempt_number == 1 else "retry",
        "test_steps": state.get("test_steps", []),
        "execution_results": result.get("execution_results", []),
        "console_errors": result.get("console_errors", []),
        "network_errors": result.get("network_errors", []),
        "screenshots": result.get("screenshots", []),
    }


def classify_issues(state: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    console_counts: dict[str, int] = {}
    for error in state.get("console_errors", []):
        text = error.get("text", "Console error")
        console_counts[text] = console_counts.get(text, 0) + 1
    for text, count in console_counts.items():
        issues.append(
            {
                "severity": console_issue_severity(text),
                "kind": "console",
                "message": text if count == 1 else f"{text} (repeated {count} times)",
                "count": count,
                "reproduction_steps": ["打开页面并检查浏览器控制台"],
            }
        )
    for error in state.get("network_errors", []):
        status = error.get("status", "unknown")
        issues.append(
            {
                "severity": "high" if int(status) >= 500 else "medium",
                "kind": "network",
                "message": f"Network request failed with status {status}: {error.get('url', '')}",
                "reproduction_steps": ["Open the page and monitor network requests"],
            }
        )
    for result in state.get("execution_results", []):
        if not result.get("ok", False):
            issues.append(
                {
                    "severity": "medium",
                    "kind": "interaction",
                    "message": result.get("error", "Interaction failed"),
                    "reproduction_steps": [result.get("description", "Run the interaction step")],
                }
            )
    return issues


def console_issue_severity(message: str) -> str:
    lowered = message.lower()
    resource_failure_markers = [
        "failed to load resource",
        "net::err_connection_reset",
        "net::err_failed",
        "net::err_name_not_resolved",
        "net::err_connection_refused",
    ]
    if any(marker in lowered for marker in resource_failure_markers):
        return "medium"
    return "high"


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(issue)
    steps = normalized.get("reproduction_steps", [])
    if isinstance(steps, str):
        normalized["reproduction_steps"] = [line.strip() for line in steps.splitlines() if line.strip()]
    elif isinstance(steps, list):
        normalized["reproduction_steps"] = [str(step) for step in steps]
    else:
        normalized["reproduction_steps"] = []
    return normalized


def render_report(state: dict[str, Any]) -> str:
    lines = [
        "# Browser QA Report",
        "",
        f"- URL: {state.get('url', '')}",
        f"- Title: {state.get('title', '')}",
        f"- Issues found: {len(state.get('issues', []))}",
        "",
        "## Test Steps",
    ]
    summary_steps = state.get("planned_steps") or state.get("test_steps", [])
    for index, step in enumerate(summary_steps, start=1):
        lines.append(f"{index}. {step.get('description', step.get('action', 'Step'))}")
    lines.extend(["", "## Attempts"])
    if state.get("attempts"):
        for attempt in state.get("attempts", []):
            lines.extend(
                [
                    f"### Attempt {attempt.get('attempt')} - {attempt.get('phase', 'unknown')}",
                    "",
                    "Steps:",
                ]
            )
            for index, step in enumerate(attempt.get("test_steps", []), start=1):
                lines.append(f"{index}. {step.get('description', step.get('action', 'Step'))}")
            lines.extend(["", "Results:"])
            for index, result in enumerate(attempt.get("execution_results", []), start=1):
                status = "PASS" if result.get("ok") else "FAIL"
                lines.append(f"{index}. [{status}] {result.get('description', result.get('action', 'Step'))}")
                if result.get("error"):
                    lines.append(f"   Error: {result.get('error')}")
            lines.extend(["", "Screenshots:"])
            for screenshot in attempt.get("screenshots", []):
                lines.append(f"- {screenshot}")
            lines.append("")
            lines.append(f"Console errors: {len(attempt.get('console_errors', []))}")
            lines.append(f"Network errors: {len(attempt.get('network_errors', []))}")
            lines.append("")
    else:
        lines.append("No attempt details recorded.")
    lines.extend(["", "## Issues"])
    if state.get("issues"):
        for issue in state.get("issues", []):
            lines.extend(
                [
                    f"### {issue.get('severity', 'unknown').title()} - {issue.get('kind', 'issue')}",
                    issue.get("message", ""),
                    "",
                    "Reproduction:",
                ]
            )
            for step in issue.get("reproduction_steps", []):
                lines.append(f"- {step}")
            lines.append("")
    else:
        lines.append("No issues detected by the current checks.")
    lines.extend(["", "## Screenshots"])
    for screenshot in state.get("screenshots", []):
        lines.append(f"- {screenshot}")
    lines.extend(["", "## Raw Signals"])
    lines.append(f"- Console errors: {len(state.get('console_errors', []))}")
    lines.append(f"- Network errors: {len(state.get('network_errors', []))}")
    return "\n".join(lines).strip() + "\n"
