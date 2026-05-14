from app.services.browser import (
    component_key,
    component_scenarios_from_page,
    component_test_step,
    screenshot_filename,
    should_test_component,
)


def test_screenshot_filename_includes_attempt_number() -> None:
    assert screenshot_filename(1, 2) == "attempt-1-step-2.png"
    assert screenshot_filename(2, 1) == "attempt-2-step-1.png"


def test_component_key_prefers_selector_and_kind() -> None:
    assert component_key({"kind": "button", "selector": "#save", "text": "Save"}) == "button:#save"


def test_should_test_component_skips_disabled_component() -> None:
    assert should_test_component({"kind": "button", "selector": "#save", "disabled": True}) is False


def test_component_test_step_clicks_buttons_and_links() -> None:
    step = component_test_step({"kind": "button", "selector": "#add", "text": "Add Element"})

    assert step["action"] == "click"
    assert step["selector"] == "#add"


def test_component_test_step_fills_text_inputs() -> None:
    step = component_test_step({"kind": "input", "selector": "#email", "placeholder": "Email"})

    assert step["action"] == "fill"
    assert step["value"] == "qa@example.com"


def test_component_test_step_toggles_checkboxes() -> None:
    step = component_test_step({"kind": "input", "type": "checkbox", "selector": "#terms", "label": "Terms"})

    assert step["action"] == "check"


def test_component_scenarios_from_page_can_skip_already_seen_components() -> None:
    page = {
        "elements": [
            {"kind": "button", "text": "Add Element", "selector": "button:nth-of-type(1)"},
            {"kind": "button", "text": "Delete", "selector": ".added-manually"},
        ],
    }

    scenarios = component_scenarios_from_page(page, max_components=10, seen_keys={"button:text:Add Element"})

    assert len(scenarios) == 1
    assert scenarios[0]["name"] == "组件流程：Delete"
    assert scenarios[0]["steps"][0]["description"] == "测试组件：点击 Delete"
