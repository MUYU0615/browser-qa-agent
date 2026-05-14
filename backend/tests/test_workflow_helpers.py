import asyncio

from app.graph.nodes import (
    build_attempt,
    classify_issues,
    component_coverage_executor_node,
    console_issue_severity,
    is_dangerous_step,
    is_redundant_step,
    normalize_issue,
    plan_retry_steps,
    render_report,
    stepwise_executor_node,
)


class FakeStepwiseStore:
    def __init__(self) -> None:
        self.llm_calls: list[dict] = []
        self.events: list[tuple[str, str]] = []
        self.updates: list[dict] = []

    def update_run(self, run_id: str, **kwargs) -> None:
        self.updates.append({"run_id": run_id, **kwargs})

    def append_event(self, run_id: str, node: str, message: str) -> None:
        self.events.append((node, message))

    def append_llm_call(self, run_id: str, trace: dict) -> None:
        self.llm_calls.append({"run_id": run_id, **trace})


class FakeStepwiseLlm:
    def __init__(self) -> None:
        self.pages: list[dict] = []

    async def plan_next_step_with_trace(
        self,
        url: str,
        page: dict,
        history: list[dict],
        current_step: int,
        max_steps: int,
    ) -> dict:
        self.pages.append(page)
        texts = [element.get("text") for element in page.get("elements", [])]
        if "Delete" in texts:
            step = {"description": "Click Delete", "action": "click", "selector": ".added-manually"}
        else:
            step = {"description": "Click Add Element", "action": "click", "selector": "button"}
        return {
            "purpose": "plan_next_step",
            "called_model": False,
            "model": "fake",
            "base_url": "fake",
            "prompt": "",
            "raw_output": "",
            "parsed_output": {"should_stop": False, "step": step, "reason": "test"},
            "fallback_reason": "test",
        }


class FakeStepwiseBrowser:
    async def execute_stepwise(self, url: str, run_id: str, planner, max_steps: int = 5) -> dict:
        first_page = {
            "title": "The Internet",
            "elements": [{"kind": "button", "text": "Add Element", "selector": "button"}],
        }
        first_trace = await planner(first_page, [], 1, max_steps)
        first_result = {**first_trace["parsed_output"]["step"], "ok": True, "error": None}
        second_page = {
            "title": "The Internet",
            "elements": [
                {"kind": "button", "text": "Add Element", "selector": "button"},
                {"kind": "button", "text": "Delete", "selector": ".added-manually"},
            ],
        }
        second_trace = await planner(second_page, [first_result], 2, max_steps)
        second_result = {**second_trace["parsed_output"]["step"], "ok": True, "error": None}
        return {
            "title": second_page["title"],
            "elements": second_page["elements"],
            "test_steps": [first_trace["parsed_output"]["step"], second_trace["parsed_output"]["step"]],
            "execution_results": [first_result, second_result],
            "console_errors": [],
            "network_errors": [],
            "screenshots": [],
        }


class FakeScenarioLlm:
    async def plan_component_scenarios_with_trace(self, url: str, page: dict, max_components: int = 25) -> dict:
        return {
            "purpose": "plan_component_scenarios",
            "called_model": False,
            "model": "fake",
            "base_url": "fake",
            "prompt": "",
            "raw_output": "",
            "parsed_output": [
                {
                    "name": "Login flow",
                    "target_components": ["#username", "#password", "#login"],
                    "steps": [
                        {"description": "Fill username", "action": "fill", "selector": "#username", "value": "qa_user"},
                        {"description": "Fill password", "action": "fill", "selector": "#password", "value": "Password123!"},
                        {"description": "Click Login", "action": "click", "selector": "#login"},
                    ],
                }
            ],
            "fallback_reason": "test",
        }


class FakeScenarioBrowser:
    def __init__(self) -> None:
        self.scenarios: list[dict] = []

    async def execute_component_coverage(self, url: str, run_id: str, max_components: int = 25, scenarios=None) -> dict:
        self.scenarios = scenarios or []
        steps = self.scenarios[0]["steps"]
        return {
            "title": "Login",
            "elements": [],
            "test_steps": steps,
            "execution_results": [{**step, "ok": True, "error": None} for step in steps],
            "console_errors": [],
            "network_errors": [],
            "screenshots": [],
            "attempts": [
                {
                    "attempt": 1,
                    "phase": "scenario",
                    "target": "Login flow",
                    "test_steps": steps,
                    "execution_results": [{**step, "ok": True, "error": None} for step in steps],
                    "console_errors": [],
                    "network_errors": [],
                    "screenshots": [],
                }
            ],
        }


def test_classify_issues_turns_console_and_network_errors_into_issues() -> None:
    state = {
        "url": "https://example.com",
        "console_errors": [{"type": "error", "text": "ReferenceError: x is not defined"}],
        "network_errors": [{"url": "https://example.com/api", "status": 500}],
        "execution_results": [{"ok": False, "description": "Click submit", "error": "Timeout"}],
    }

    issues = classify_issues(state)

    assert [issue["kind"] for issue in issues] == ["console", "network", "interaction"]
    assert issues[0]["severity"] == "high"
    assert issues[1]["severity"] == "high"
    assert issues[2]["reproduction_steps"] == ["Click submit"]


def test_classify_issues_deduplicates_repeated_console_resource_errors() -> None:
    state = {
        "url": "https://example.com",
        "console_errors": [
            {"type": "error", "text": "Failed to load resource: net::ERR_CONNECTION_RESET"},
            {"type": "error", "text": "Failed to load resource: net::ERR_CONNECTION_RESET"},
            {"type": "error", "text": "Failed to load resource: net::ERR_CONNECTION_RESET"},
        ],
        "network_errors": [],
        "execution_results": [],
    }

    issues = classify_issues(state)

    assert len(issues) == 1
    assert issues[0]["kind"] == "console"
    assert issues[0]["severity"] == "medium"
    assert issues[0]["count"] == 3


def test_console_issue_severity_keeps_runtime_errors_high() -> None:
    assert console_issue_severity("Cannot read properties of null") == "high"
    assert console_issue_severity("ReferenceError: x is not defined") == "high"
    assert console_issue_severity("Failed to load resource: net::ERR_CONNECTION_RESET") == "medium"


def test_script_payload_steps_are_treated_as_unsafe() -> None:
    step = {"action": "fill", "selector": "#username", "value": "<script>alert('XSS')</script>"}

    assert is_dangerous_step(step) is True


def test_dynamic_delete_button_is_not_treated_as_account_deletion() -> None:
    step = {"action": "click", "selector": ".added-manually", "description": "Click Delete"}

    assert is_dangerous_step(step) is False


def test_account_delete_step_is_treated_as_unsafe() -> None:
    step = {"action": "click", "selector": "#delete-account", "description": "Delete account"}

    assert is_dangerous_step(step) is True


def test_repeated_successful_click_is_redundant() -> None:
    step = {"action": "click", "selector": "#add", "description": "Click Add Element again"}
    history = [{"action": "click", "selector": "#add", "ok": True}]

    assert is_redundant_step(step, history) is True


def test_new_click_target_is_not_redundant() -> None:
    step = {"action": "click", "selector": ".added-manually", "description": "Click Delete"}
    history = [{"action": "click", "selector": "#add", "ok": True}]

    assert is_redundant_step(step, history) is False


def test_retry_plan_replays_setup_steps_through_first_failure() -> None:
    steps = [
        {"action": "click", "selector": "a[href='/login']", "description": "Open login"},
        {"action": "fill", "selector": "#username", "value": "qa@example.com", "description": "Fill username"},
        {"action": "click", "selector": "button[type='submit']", "description": "Submit form"},
        {"action": "assert_text", "text": "Welcome", "description": "Check result"},
    ]
    results = [
        {"ok": True},
        {"ok": True},
        {"ok": True},
        {"ok": False, "error": "Timeout"},
    ]

    assert plan_retry_steps(steps, results) == steps


def test_retry_plan_drops_unsafe_setup_steps() -> None:
    steps = [
        {"action": "fill", "selector": "#username", "value": "<script>alert('XSS')</script>"},
        {"action": "assert_text", "text": "<script>alert('XSS')</script>"},
    ]
    results = [{"ok": True}, {"ok": False, "error": "Timeout"}]

    assert plan_retry_steps(steps, results) == []


def test_stepwise_executor_replans_from_updated_dom() -> None:
    store = FakeStepwiseStore()
    llm = FakeStepwiseLlm()
    state = {
        "run_id": "run-1",
        "url": "https://example.com/add_remove_elements",
        "run_store": store,
        "browser": FakeStepwiseBrowser(),
        "llm": llm,
        "screenshots": [],
        "console_errors": [],
        "network_errors": [],
    }

    result = asyncio.run(stepwise_executor_node(state))

    assert llm.pages[0]["elements"] == [{"kind": "button", "text": "Add Element", "selector": "button"}]
    assert llm.pages[1]["elements"][1]["text"] == "Delete"
    assert result["test_steps"][1]["description"] == "Click Delete"
    assert [call["purpose"] for call in store.llm_calls] == ["plan_next_step", "plan_next_step"]


def test_component_coverage_executor_uses_llm_scenarios() -> None:
    store = FakeStepwiseStore()
    browser = FakeScenarioBrowser()
    state = {
        "run_id": "run-1",
        "url": "https://example.com/login",
        "title": "Login",
        "elements": [
            {"kind": "input", "label": "username", "selector": "#username"},
            {"kind": "input", "label": "password", "type": "password", "selector": "#password"},
            {"kind": "button", "text": "Login", "selector": "#login"},
        ],
        "run_store": store,
        "browser": browser,
        "llm": FakeScenarioLlm(),
        "screenshots": [],
        "console_errors": [],
        "network_errors": [],
    }

    result = asyncio.run(component_coverage_executor_node(state))

    assert len(browser.scenarios) == 1
    assert [step["selector"] for step in browser.scenarios[0]["steps"]] == ["#username", "#password", "#login"]
    assert [call["purpose"] for call in store.llm_calls] == ["plan_component_scenarios"]
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["phase"] == "scenario"


def test_render_report_includes_summary_steps_issues_and_screenshots() -> None:
    state = {
        "url": "https://example.com",
        "title": "Demo",
        "test_steps": [{"description": "Check title"}, {"description": "Click Search"}],
        "issues": [{"severity": "medium", "kind": "interaction", "message": "Button timed out"}],
        "screenshots": ["runs/abc/initial.png", "runs/abc/final.png"],
        "console_errors": [],
        "network_errors": [],
    }

    report = render_report(state)

    assert "# Browser QA Report" in report
    assert "https://example.com" in report
    assert "Click Search" in report
    assert "Button timed out" in report
    assert "runs/abc/final.png" in report


def test_build_attempt_captures_steps_results_and_attempt_number() -> None:
    state = {
        "retry_count": 1,
        "test_steps": [{"description": "重试检查标题", "action": "assert_title"}],
    }
    result = {
        "execution_results": [{"ok": True, "description": "重试检查标题"}],
        "console_errors": [{"text": "console failed"}],
        "network_errors": [],
        "screenshots": ["/runs/abc/retry-step-1.png"],
    }

    attempt = build_attempt(state, result)

    assert attempt["attempt"] == 2
    assert attempt["phase"] == "retry"
    assert attempt["test_steps"] == state["test_steps"]
    assert attempt["execution_results"] == result["execution_results"]
    assert attempt["console_errors"] == result["console_errors"]
    assert attempt["screenshots"] == result["screenshots"]


def test_render_report_includes_each_attempt_separately() -> None:
    state = {
        "url": "https://example.com",
        "title": "Demo",
        "test_steps": [{"description": "最终检查"}],
        "issues": [],
        "screenshots": [],
        "console_errors": [],
        "network_errors": [],
        "attempts": [
            {
                "attempt": 1,
                "phase": "initial",
                "test_steps": [{"description": "第一次点击搜索"}],
                "execution_results": [{"ok": False, "description": "第一次点击搜索", "error": "Timeout"}],
                "console_errors": [],
                "network_errors": [],
                "screenshots": ["/runs/abc/step-1.png"],
            },
            {
                "attempt": 2,
                "phase": "retry",
                "test_steps": [{"description": "重试检查标题"}],
                "execution_results": [{"ok": True, "description": "重试检查标题", "error": None}],
                "console_errors": [],
                "network_errors": [],
                "screenshots": ["/runs/abc/retry-step-1.png"],
            },
        ],
    }

    report = render_report(state)

    assert "## Attempts" in report
    assert "### Attempt 1 - initial" in report
    assert "第一次点击搜索" in report
    assert "Timeout" in report
    assert "### Attempt 2 - retry" in report
    assert "重试检查标题" in report
    assert "/runs/abc/retry-step-1.png" in report


def test_normalize_issue_turns_string_reproduction_steps_into_list() -> None:
    issue = {
        "severity": "high",
        "kind": "security",
        "message": "发现验证码跳转",
        "reproduction_steps": "1. 打开页面\n2. 点击搜索",
    }

    normalized = normalize_issue(issue)

    assert normalized["reproduction_steps"] == ["1. 打开页面", "2. 点击搜索"]
