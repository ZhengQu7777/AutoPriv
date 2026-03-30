from __future__ import annotations

from typing import Any
import json

from autopriv.agents.base import Agent
from autopriv.llm import LLMClient
from autopriv.orchestration.blackboard import Blackboard
from autopriv.prompting.prompt_store import render_prompt
from autopriv.settings import AppSettings, load_settings
from autopriv.types import PlannerAction, PlannerOutput, ProbePlan


class PlannerAgent(Agent):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__(name="planner")
        self.settings = settings or load_settings()
        self.llm = LLMClient(self.settings)

    def _run_llm(self, instruction: str) -> PlannerOutput:
        system_prompt = render_prompt("planner_system.txt")
        user_prompt = render_prompt("planner_user.txt", {"TASK": instruction})
        payload = self.llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        goals = payload.get("goals", [])
        constraints = payload.get("constraints", {})
        probe_plan = _parse_probe_plan(payload.get("probe_plan", {}), instruction)
        if not isinstance(goals, list):
            goals = ["auto_configure"]
        if not isinstance(constraints, dict):
            constraints = {}
        if not goals:
            goals = ["auto_configure"]
        return PlannerOutput(
            instruction=instruction.strip(),
            goals=[str(g) for g in goals],
            constraints=constraints,
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

    def decide_next(
        self,
        instruction: str,
        state: dict[str, Any],
        observation: dict[str, Any] | None = None,
        blackboard: Blackboard | None = None,
    ) -> PlannerAction:
        system_prompt = render_prompt("planner_decide_system.txt")
        user_prompt = render_prompt(
            "planner_decide_user.txt",
            {
                "TASK": instruction,
                "STATE_JSON": json.dumps(state, ensure_ascii=False),
                "OBS_JSON": json.dumps(observation or {}, ensure_ascii=False),
                "COMM_TRACE_JSON": json.dumps(blackboard.to_dict() if blackboard is not None else [], ensure_ascii=False),
            },
        )
        payload = self.llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        action = _parse_action(payload)
        if blackboard is not None:
            blackboard.publish(
                sender="planner",
                receiver="pipeline",
                kind="next_action",
                content={
                    "agent": action.agent,
                    "purpose": action.purpose,
                    "done": action.done,
                    "updates": action.updates,
                },
            )
        return action


def _parse_probe_plan(raw: Any, instruction: str) -> ProbePlan:
    if not isinstance(raw, dict):
        return ProbePlan(prober_prompt=render_prompt("prober_default.txt", {"TASK": instruction}))

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
        prober_prompt=str(raw.get("prober_prompt", render_prompt("prober_default.txt", {"TASK": instruction}))),
    )


def _parse_action(payload: Any) -> PlannerAction:
    if not isinstance(payload, dict):
        return PlannerAction(agent="prober", purpose="collect signals")

    agent = str(payload.get("agent", "prober")).strip().lower()
    if agent not in {"prober", "configer", "critic", "executor", "stop"}:
        agent = "prober"

    updates = payload.get("updates", {})
    if not isinstance(updates, dict):
        updates = {}

    done_raw = payload.get("done", False)
    done = bool(done_raw)
    if agent == "stop":
        done = True

    return PlannerAction(
        agent=agent,
        purpose=str(payload.get("purpose", "")).strip(),
        done=done,
        updates=updates,
    )
