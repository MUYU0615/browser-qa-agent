from __future__ import annotations

import asyncio
import json
import re
from typing import Any


def extract_json_array(text: str) -> list[dict[str, Any]]:
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else _extract_first_array(text)
    if not candidate:
        return []
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def extract_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else _extract_first_object(text)
    if not candidate:
        return {}
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_first_array(text: str) -> str:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _extract_first_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


class LLMClient:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def plan_steps(self, url: str, page: dict[str, Any]) -> list[dict[str, Any]]:
        trace = await self.plan_steps_with_trace(url, page)
        return trace["parsed_output"]

    async def plan_steps_with_trace(self, url: str, page: dict[str, Any]) -> dict[str, Any]:
        prompt = build_planner_prompt(url, page)
        if not self.api_key:
            return self._fallback_trace(
                purpose="plan_steps",
                prompt=prompt,
                parsed_output=fallback_steps(page),
                fallback_reason="missing_api_key",
            )

        try:
            text = await self._complete(prompt)
        except Exception as exc:
            return {
                "purpose": "plan_steps",
                "called_model": True,
                "model": self.model,
                "base_url": self.base_url,
                "prompt": prompt,
                "raw_output": "",
                "parsed_output": fallback_steps(page),
                "fallback_reason": "model_call_failed",
                "error": str(exc) or repr(exc),
            }
        steps = extract_json_array(text)
        fallback_reason = "" if steps else "model_output_not_parseable"
        return {
            "purpose": "plan_steps",
            "called_model": True,
            "model": self.model,
            "base_url": self.base_url,
            "prompt": prompt,
            "raw_output": text,
            "parsed_output": steps or fallback_steps(page),
            "fallback_reason": fallback_reason,
        }

    async def judge_observations(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        trace = await self.judge_observations_with_trace(state)
        return trace["parsed_output"]

    async def plan_next_step_with_trace(
        self,
        url: str,
        page: dict[str, Any],
        history: list[dict[str, Any]],
        current_step: int,
        max_steps: int,
    ) -> dict[str, Any]:
        prompt = build_next_step_prompt(url, page, history, current_step, max_steps)
        fallback = fallback_next_step(page, history, current_step, max_steps)
        if not self.api_key:
            return self._fallback_trace(
                purpose="plan_next_step",
                prompt=prompt,
                parsed_output=fallback,
                fallback_reason="missing_api_key",
            )

        try:
            text = await self._complete(prompt)
        except Exception as exc:
            return {
                "purpose": "plan_next_step",
                "called_model": True,
                "model": self.model,
                "base_url": self.base_url,
                "prompt": prompt,
                "raw_output": "",
                "parsed_output": fallback,
                "fallback_reason": "model_call_failed",
                "error": str(exc) or repr(exc),
            }
        parsed = extract_json_object(text)
        return {
            "purpose": "plan_next_step",
            "called_model": True,
            "model": self.model,
            "base_url": self.base_url,
            "prompt": prompt,
            "raw_output": text,
            "parsed_output": parsed or fallback,
            "fallback_reason": "" if parsed else "model_output_not_parseable",
        }

    async def judge_observations_with_trace(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = build_judge_prompt(state)
        if not self.api_key:
            return self._fallback_trace(
                purpose="judge_observations",
                prompt=prompt,
                parsed_output=[],
                fallback_reason="missing_api_key",
            )

        try:
            text = await self._complete(prompt)
        except Exception as exc:
            return {
                "purpose": "judge_observations",
                "called_model": True,
                "model": self.model,
                "base_url": self.base_url,
                "prompt": prompt,
                "raw_output": "",
                "parsed_output": [],
                "fallback_reason": "model_call_failed",
                "error": str(exc) or repr(exc),
            }
        issues = extract_json_array(text)
        return {
            "purpose": "judge_observations",
            "called_model": True,
            "model": self.model,
            "base_url": self.base_url,
            "prompt": prompt,
            "raw_output": text,
            "parsed_output": issues,
            "fallback_reason": "",
        }

    async def _complete(self, prompt: str) -> str:
        def call() -> str:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=30.0)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Return concise machine-readable JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content or ""

        return await asyncio.to_thread(call)

    def _fallback_trace(
        self,
        purpose: str,
        prompt: str,
        parsed_output: Any,
        fallback_reason: str,
    ) -> dict[str, Any]:
        return {
            "purpose": purpose,
            "called_model": False,
            "model": self.model,
            "base_url": self.base_url,
            "prompt": prompt,
            "raw_output": "",
            "parsed_output": parsed_output,
            "fallback_reason": fallback_reason,
        }


def build_planner_prompt(url: str, page: dict[str, Any]) -> str:
    return (
        "你是浏览器 QA 测试规划 Agent。只返回 JSON 数组，生成 3 到 5 个安全测试步骤。"
        "允许的 action 只有：assert_title、assert_text、click、fill。"
        "每个步骤必须包含 description 和 action，必要时包含 selector、value、text。"
        "description 字段必须使用中文；action、selector、value、text 字段保持英文或原始选择器。"
        "跳过支付、删除、退订、下单、购买等高风险或不可逆操作。\n\n"
        f"URL: {url}\nPage summary:\n{json.dumps(page, ensure_ascii=False)}"
    )


def build_judge_prompt(state: dict[str, Any]) -> str:
    return (
        "你是 QA 缺陷判断 Agent。只返回 JSON 数组。"
        "每个 issue 必须包含 severity、kind、message、reproduction_steps。"
        "message 和 reproduction_steps 必须使用中文；severity 和 kind 保持英文枚举值。\n\n"
        f"State:\n{json.dumps(state, ensure_ascii=False, default=str)}"
    )


def build_next_step_prompt(
    url: str,
    page: dict[str, Any],
    history: list[dict[str, Any]],
    current_step: int,
    max_steps: int,
) -> str:
    return (
        "你是浏览器 QA 测试规划 Agent。只生成下一步动作，并只返回 JSON 对象。"
        "对象格式为 {\"should_stop\": boolean, \"step\": object|null, \"reason\": string}。"
        "允许的 action 只有：assert_title、assert_text、click、fill。"
        "description 字段必须使用中文；action、selector、value、text 字段保持英文或原始选择器。"
        "不要生成脚本注入、支付、删除、退订、下单、购买等高风险动作。"
        "max_steps 是上限，不是必须跑满的目标。"
        "核心流程已经验证完成时必须返回 should_stop=true，不要重复点击已经成功点击过的元素。"
        f"\n\nURL: {url}\nStep: {current_step}/{max_steps}\n"
        f"History:\n{json.dumps(history, ensure_ascii=False, default=str)}\n"
        f"Page summary:\n{json.dumps(page, ensure_ascii=False, default=str)}"
    )


def fallback_steps(page: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"description": "确认页面标题已加载", "action": "assert_title"}
    ]
    elements = page.get("elements", [])
    for element in elements:
        if element.get("kind") in {"input", "textarea"} and len(steps) < 5:
            field_name = element.get("label") or element.get("placeholder") or "输入框"
            steps.append(
                {
                    "description": f"填写{field_name}",
                    "action": "fill",
                    "selector": element.get("selector"),
                    "value": "qa@example.com",
                }
            )
        if element.get("kind") in {"button", "link"} and len(steps) < 5:
            text = element.get("text") or element.get("label") or element.get("selector")
            steps.append(
                {
                    "description": f"点击{text}",
                    "action": "click",
                    "selector": element.get("selector"),
                }
            )
        if len(steps) >= 5:
            break
    if len(steps) == 1:
        steps.append({"description": "检查页面是否显示标题文本", "action": "assert_text", "text": page.get("title", "")})
    return steps


def fallback_next_step(
    page: dict[str, Any],
    history: list[dict[str, Any]],
    current_step: int,
    max_steps: int,
) -> dict[str, Any]:
    if current_step > max_steps:
        return {"should_stop": True, "step": None, "reason": "max_steps_reached"}

    used_actions = [step.get("action") for step in history]
    filled_selectors = {step.get("selector") for step in history if step.get("action") == "fill"}
    clicked_selectors = {step.get("selector") for step in history if step.get("action") == "click"}
    if "assert_title" not in used_actions:
        return {
            "should_stop": False,
            "step": {"description": "确认页面标题已加载", "action": "assert_title"},
            "reason": "check_title_first",
        }

    for element in page.get("elements", []):
        if element.get("kind") in {"input", "textarea"} and element.get("selector") not in filled_selectors:
            field_name = element.get("label") or element.get("placeholder") or "输入框"
            return {
                "should_stop": False,
                "step": {
                    "description": f"填写{field_name}",
                    "action": "fill",
                    "selector": element.get("selector"),
                    "value": "qa@example.com",
                },
                "reason": "fill_first_input",
            }

    for element in page.get("elements", []):
        if element.get("kind") in {"button", "link"} and element.get("selector") not in clicked_selectors:
            text = element.get("text") or element.get("label") or element.get("selector")
            return {
                "should_stop": False,
                "step": {"description": f"点击{text}", "action": "click", "selector": element.get("selector")},
                "reason": "click_first_actionable",
            }

    return {"should_stop": True, "step": None, "reason": "no_actionable_element"}
