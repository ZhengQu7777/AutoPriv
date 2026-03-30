from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from autopriv.agents.base import Agent
from autopriv.llm import LLMClient
from autopriv.orchestration.blackboard import Blackboard
from autopriv.prompting.prompt_store import render_prompt
from autopriv.settings import AppSettings, load_settings
from autopriv.types import ConfigOutput, CriticOutput, PlannerOutput, ProbeReport


class CriticAgent(Agent):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__(name="critic")
        self.settings = settings or load_settings()
        self.llm = LLMClient(self.settings)

    def run(
        self,
        planner: PlannerOutput,
        probe_report: ProbeReport,
        config: ConfigOutput,
        blackboard: Blackboard | None = None,
        **kwargs: Any,
    ) -> CriticOutput:
        static_issues, static_next = _static_checks(probe_report, config)
        payload = self.llm.chat_json(
            system_prompt=render_prompt("critic_system.txt"),
            user_prompt=render_prompt(
                "critic_user.txt",
                {
                    "PLANNER_JSON": json.dumps(asdict(planner), ensure_ascii=False),
                    "PROBE_REPORT_JSON": json.dumps(probe_report.to_dict(), ensure_ascii=False),
                    "CONFIG_JSON": json.dumps(config.to_dict(), ensure_ascii=False),
                    "COMM_TRACE_JSON": json.dumps(blackboard.to_dict() if blackboard is not None else [], ensure_ascii=False),
                },
            ),
        )
        out = _parse_output(payload)
        out.issues = list(dict.fromkeys(static_issues + out.issues))
        if static_issues:
            out.approved = False
            if out.next_agent == "executor":
                out.next_agent = static_next
        if blackboard is not None:
            blackboard.publish(
                sender="critic",
                receiver="pipeline",
                kind="critic_verdict",
                content=out.to_dict(),
            )
        return out



def _static_checks(probe_report: ProbeReport, config: ConfigOutput) -> tuple[list[str], str]:
    issues: list[str] = []
    summary = probe_report.summary
    max_rtt = summary.get("max_rtt_ms")
    min_bw = summary.get("min_bandwidth_mbps")

    if isinstance(max_rtt, (int, float)) and max_rtt > 300 and config.mode == "online_balanced":
        issues.append("RTT is too high for online_balanced mode")
    if isinstance(min_bw, (int, float)) and min_bw < 5 and config.profile != "low_bandwidth":
        issues.append("Bandwidth is very low but profile is not low_bandwidth")

    if issues:
        if "RTT is too high for online_balanced mode" in issues:
            return issues, "configer"
        return issues, "prober"
    return issues, "executor"



def _parse_output(payload: Any) -> CriticOutput:
    if not isinstance(payload, dict):
        return CriticOutput(
            approved=False,
            risk_level="high",
            issues=["Critic output malformed"],
            recommendations=["Re-run critic with valid JSON output"],
            next_agent="configer",
        )

    approved = bool(payload.get("approved", False))
    risk_level = str(payload.get("risk_level", "medium")).strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium"

    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        issues = [str(issues)]

    recs = payload.get("recommendations", [])
    if not isinstance(recs, list):
        recs = [str(recs)]

    next_agent = str(payload.get("next_agent", "executor")).strip().lower()
    if next_agent not in {"executor", "prober", "configer", "stop"}:
        next_agent = "executor"

    return CriticOutput(
        approved=approved,
        risk_level=risk_level,
        issues=[str(x) for x in issues],
        recommendations=[str(x) for x in recs],
        next_agent=next_agent,
    )
