from __future__ import annotations

from typing import Any

from autopriv.agents.base import Agent
from autopriv.llm import LLMClient
from autopriv.orchestration.blackboard import Blackboard
from autopriv.prompting.prompt_store import load_prompt
from autopriv.settings import AppSettings, load_settings
from autopriv.types import PlannerOutput, ProbePlan


class PlannerAgent(Agent):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__(name="planner")
        self.settings = settings or load_settings()
        self.llm = LLMClient(self.settings)
        self._planner_system_prompt = load_prompt("planner_system.txt")
        self._planner_user_template = load_prompt("planner_user.txt")
        self._default_prober_template = load_prompt("prober_default.txt")

    def _run_llm(self, instruction: str) -> PlannerOutput:
        system_prompt = self._planner_system_prompt
        user_prompt = _render_template(self._planner_user_template, {"TASK": instruction})
        payload = self.llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        goals = payload.get("goals", [])
        constraints = payload.get("constraints", {})
        default_prober_prompt = _render_template(self._default_prober_template, {"TASK": instruction})
        probe_plan = _parse_probe_plan(payload.get("probe_plan", {}), default_prober_prompt)
        planning_notes = payload.get("planning_notes", [])
        if not isinstance(goals, list):
            goals = ["auto_configure"]
        if not isinstance(constraints, dict):
            constraints = {}
        if not isinstance(planning_notes, list):
            planning_notes = [planning_notes]
        if not goals:
            goals = ["auto_configure"]
        return PlannerOutput(
            instruction=instruction.strip(),
            goals=[str(g) for g in goals],
            constraints=constraints,
            requires_probe=_parse_requires_probe(payload.get("requires_probe"), instruction),
            request_execute=_parse_request_execute(payload.get("request_execute"), instruction),
            planning_notes=[str(x).strip() for x in planning_notes if str(x).strip()],
            probe_plan=probe_plan,
            planner_prompt={"system": system_prompt, "user": user_prompt},
        )

    def run(self, instruction: str, blackboard: Blackboard | None = None, **kwargs: Any) -> PlannerOutput:
        out = self._run_llm(instruction)
        if blackboard is not None:
            blackboard.publish(
                sender="planner",
                receiver="prober",
                kind="probe_plan",
                content={
                    "instruction": out.instruction,
                    "goals": out.goals,
                    "constraints": out.constraints,
                    "requires_probe": out.requires_probe,
                    "request_execute": out.request_execute,
                    "planning_notes": out.planning_notes,
                    "probe_plan": {
                        "objective": out.probe_plan.objective,
                        "metrics": out.probe_plan.metrics,
                        "sample_count": out.probe_plan.sample_count,
                        "interval_s": out.probe_plan.interval_s,
                        "tool_args": out.probe_plan.tool_args,
                        "prober_prompt": out.probe_plan.prober_prompt,
                    },
                },
            )
        return out

def _parse_probe_plan(raw: Any, default_prober_prompt: str) -> ProbePlan:
    if not isinstance(raw, dict):
        return ProbePlan(prober_prompt=default_prober_prompt)

    metrics = raw.get("metrics", ["rtt_ms", "bandwidth_mbps", "cpu_cores", "memory_gb"])
    if not isinstance(metrics, list):
        metrics = ["rtt_ms", "bandwidth_mbps", "cpu_cores", "memory_gb"]

    tool_args = raw.get("tool_args", {})
    if not isinstance(tool_args, dict):
        tool_args = {}

    sample_count = raw.get("sample_count", 1)
    interval_s = raw.get("interval_s", 300.0)

    try:
        sample_count_i = max(int(sample_count), 1)
    except (TypeError, ValueError):
        sample_count_i = 1

    try:
        interval_f = max(float(interval_s), 0.0)
    except (TypeError, ValueError):
        interval_f = 300.0

    return ProbePlan(
        objective=str(raw.get("objective", "collect runtime signals for backend selection")),
        metrics=[str(m) for m in metrics],
        sample_count=sample_count_i,
        interval_s=interval_f,
        tool_args=tool_args,
        prober_prompt=str(raw.get("prober_prompt", default_prober_prompt)),
    )


def _render_template(template: str, variables: dict[str, str] | None = None) -> str:
    if not variables:
        return template
    out = template
    for key, value in variables.items():
        out = out.replace(f"[[{key}]]", value)
    return out


def _parse_requires_probe(raw: Any, instruction: str) -> bool:
    parsed = _coerce_bool(raw)
    if parsed is not None:
        return parsed
    if any(token in instruction for token in ("无需探测", "不需要探测", "跳过探测", "不探测")):
        return False
    if "简单任务" in instruction:
        return False
    return True


def _parse_request_execute(raw: Any, instruction: str) -> bool:
    parsed = _coerce_bool(raw)
    if parsed is not None:
        return parsed
    negative_tokens = ("不执行", "不要执行", "仅生成", "只生成", "只推荐", "仅推荐")
    if any(token in instruction for token in negative_tokens):
        return False
    positive_tokens = ("执行", "运行", "启动", "落地执行")
    if any(token in instruction for token in positive_tokens):
        return True
    lowered = instruction.lower()
    if "execute" in lowered or "run " in lowered:
        return True
    return False


def _coerce_bool(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"true", "yes", "1"}:
            return True
        if text in {"false", "no", "0"}:
            return False
    return None
