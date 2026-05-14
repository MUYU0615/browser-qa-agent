import asyncio

from app.services.llm import LLMClient, extract_json_array, extract_json_object


def test_extract_json_array_from_fenced_block() -> None:
    text = """Here is the plan:
```json
[{"action": "click", "selector": "button", "description": "Click CTA"}]
```
"""

    parsed = extract_json_array(text)

    assert parsed == [{"action": "click", "selector": "button", "description": "Click CTA"}]


def test_extract_json_array_from_plain_text() -> None:
    text = 'prefix [{"action": "assert_text", "text": "Welcome"}] suffix'

    parsed = extract_json_array(text)

    assert parsed == [{"action": "assert_text", "text": "Welcome"}]


def test_extract_json_array_returns_empty_for_malformed_text() -> None:
    assert extract_json_array("not json at all") == []


def test_extract_json_object_from_fenced_block() -> None:
    text = """```json
{"should_stop": false, "step": {"action": "click", "selector": "#login"}}
```"""

    parsed = extract_json_object(text)

    assert parsed["should_stop"] is False
    assert parsed["step"]["action"] == "click"


def test_plan_steps_without_api_key_uses_deterministic_fallback() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")
    page = {
        "title": "Demo",
        "elements": [
            {"kind": "button", "text": "Search", "selector": "text=Search"},
            {"kind": "input", "placeholder": "Email", "selector": "input[placeholder='Email']"},
        ],
    }

    steps = asyncio.run(client.plan_steps("https://example.com", page))

    assert len(steps) >= 2
    assert steps[0]["action"] == "assert_title"
    assert steps[0]["description"] == "确认页面标题已加载"
    assert any(step["action"] == "fill" for step in steps)


def test_planner_prompt_requires_chinese_descriptions() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")

    trace = asyncio.run(client.plan_steps_with_trace("https://example.com", {"title": "Demo", "elements": []}))

    assert "description 字段必须使用中文" in trace["prompt"]
    assert "action、selector、value、text 字段保持英文或原始选择器" in trace["prompt"]


def test_plan_steps_with_trace_marks_fallback_when_api_key_missing() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")
    page = {"title": "Demo", "elements": []}

    trace = asyncio.run(client.plan_steps_with_trace("https://example.com", page))

    assert trace["purpose"] == "plan_steps"
    assert trace["called_model"] is False
    assert trace["model"] == "deepseek-v4-pro"
    assert trace["raw_output"] == ""
    assert trace["fallback_reason"] == "missing_api_key"
    assert trace["parsed_output"][0]["action"] == "assert_title"


def test_judge_observations_with_trace_marks_fallback_when_api_key_missing() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")

    trace = asyncio.run(client.judge_observations_with_trace({"url": "https://example.com"}))

    assert trace["purpose"] == "judge_observations"
    assert trace["called_model"] is False
    assert trace["raw_output"] == ""
    assert trace["parsed_output"] == []


def test_plan_steps_with_trace_records_model_call_failure() -> None:
    client = LLMClient(api_key="sk-test", model="deepseek-v4-pro", base_url="https://api.deepseek.com")

    async def fail_complete(prompt: str) -> str:
        raise RuntimeError("network unavailable")

    client._complete = fail_complete  # type: ignore[method-assign]
    trace = asyncio.run(client.plan_steps_with_trace("https://example.com", {"title": "Demo", "elements": []}))

    assert trace["called_model"] is True
    assert trace["fallback_reason"] == "model_call_failed"
    assert "network unavailable" in trace["error"]
    assert trace["parsed_output"][0]["action"] == "assert_title"


def test_plan_next_step_with_trace_uses_stepwise_prompt_and_fallback() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")
    page = {
        "title": "Login",
        "elements": [
            {"kind": "input", "placeholder": "Username", "selector": "#username"},
            {"kind": "button", "text": "Login", "selector": "#login"},
        ],
    }

    trace = asyncio.run(client.plan_next_step_with_trace("https://example.com/login", page, [], 1, 5))

    assert "只生成下一步动作" in trace["prompt"]
    assert trace["purpose"] == "plan_next_step"
    assert trace["called_model"] is False
    assert trace["parsed_output"]["should_stop"] is False
    assert trace["parsed_output"]["step"]["action"] == "assert_title"


def test_next_step_prompt_treats_max_steps_as_limit_not_target() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")

    trace = asyncio.run(client.plan_next_step_with_trace("https://example.com", {"title": "Demo", "elements": []}, [], 1, 5))

    assert "max_steps 是上限，不是必须跑满的目标" in trace["prompt"]
    assert "核心流程已经验证完成时必须返回 should_stop=true" in trace["prompt"]


def test_plan_next_step_fallback_moves_to_input_after_title_check() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")
    history = [{"ok": True, "action": "assert_title", "description": "确认页面标题已加载"}]
    page = {
        "title": "Login",
        "elements": [
            {"kind": "input", "placeholder": "Username", "selector": "#username"},
            {"kind": "button", "text": "Login", "selector": "#login"},
        ],
    }

    trace = asyncio.run(client.plan_next_step_with_trace("https://example.com/login", page, history, 2, 5))

    assert trace["parsed_output"]["step"]["action"] == "fill"
    assert trace["parsed_output"]["step"]["selector"] == "#username"


def test_plan_next_step_fallback_prefers_newly_observed_button() -> None:
    client = LLMClient(api_key="", model="deepseek-v4-pro", base_url="https://api.deepseek.com")
    history = [
        {"ok": True, "action": "assert_title", "description": "Check title"},
        {"ok": True, "action": "click", "description": "Click Add Element", "selector": "button"},
    ]
    page = {
        "title": "The Internet",
        "elements": [
            {"kind": "button", "text": "Add Element", "selector": "button"},
            {"kind": "button", "text": "Delete", "selector": ".added-manually"},
        ],
    }

    trace = asyncio.run(client.plan_next_step_with_trace("https://example.com/add_remove_elements", page, history, 3, 5))

    assert trace["parsed_output"]["step"]["action"] == "click"
    assert trace["parsed_output"]["step"]["selector"] == ".added-manually"
