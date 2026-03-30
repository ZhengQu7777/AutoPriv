from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from autopriv.agents.base import Agent
from autopriv.knowledge.expert_kb import ExpertKnowledgeBase
from autopriv.llm import LLMClient
from autopriv.orchestration.blackboard import Blackboard
from autopriv.prompting.prompt_store import render_prompt
from autopriv.settings import AppSettings, load_settings
from autopriv.types import ConfigOutput, PlannerOutput, ProbeOutput


class ConfigerAgent(Agent):
    def __init__(self, kb: ExpertKnowledgeBase | None = None, settings: AppSettings | None = None) -> None:
        super().__init__(name="configer")
        self.kb = kb or ExpertKnowledgeBase()
        self.settings = settings or load_settings()
        self.llm = LLMClient(self.settings)

    def run(
        self,
        planner: PlannerOutput,
        probe: ProbeOutput,
        blackboard: Blackboard | None = None,
        **kwargs: Any,
    ) -> ConfigOutput:
        backend = _choose_backend(planner, probe)
        mode = _choose_mode(probe)
        parallelism = _choose_parallelism(probe)
        profile = _choose_profile(probe)

        hits = self.kb.retrieve(planner=planner, probe=probe)
        backend, mode, profile, hit_notes = _apply_kb_hints(hits, backend, mode, profile)
        backend, mode, profile = self._llm_refine(
            planner=planner,
            probe=probe,
            backend=backend,
            mode=mode,
            profile=profile,
            hits=hits,
            blackboard=blackboard,
        )

        notes = []
        if probe.rtt_ms is None:
            notes.append("RTT unavailable, fallback to conservative defaults")
        if probe.bandwidth_mbps is None:
            notes.append("Bandwidth unavailable, use low-transfer policy")
        notes.extend(hit_notes)

        extra = {
            "goals": planner.goals,
            "constraints": planner.constraints,
            "probe": probe.raw,
            "probe_plan": {
                "objective": planner.probe_plan.objective,
                "metrics": planner.probe_plan.metrics,
                "sample_count": planner.probe_plan.sample_count,
                "interval_s": planner.probe_plan.interval_s,
                "tool_args": planner.probe_plan.tool_args,
                "prober_prompt": planner.probe_plan.prober_prompt,
            },
            "kb_hits": hits,
            "model": {
                "enabled": self.settings.model.enabled if self.settings.model else False,
                "base_url": self.settings.model.base_url if self.settings.model else None,
                "model": self.settings.model.model if self.settings.model else None,
            },
            "comm_trace": blackboard.to_dict() if blackboard is not None else [],
        }

        if blackboard is not None:
            blackboard.publish(
                sender="configer",
                receiver="pipeline",
                kind="config_output",
                content={
                    "backend": backend,
                    "mode": mode,
                    "parallelism": parallelism,
                    "profile": profile,
                    "notes": notes,
                },
            )

        return ConfigOutput(
            backend=backend,
            mode=mode,
            parallelism=parallelism,
            profile=profile,
            notes=notes,
            extra=extra,
        )

    def _llm_refine(
        self,
        planner: PlannerOutput,
        probe: ProbeOutput,
        backend: str,
        mode: str,
        profile: str,
        hits: list[dict[str, Any]],
        blackboard: Blackboard | None,
    ) -> tuple[str, str, str]:
        payload = self.llm.chat_json(
            system_prompt=render_prompt("configer_system.txt"),
            user_prompt=render_prompt(
                "configer_user.txt",
                {
                    "PLANNER_JSON": json.dumps(asdict(planner), ensure_ascii=False),
                    "PROBE_JSON": json.dumps(asdict(probe), ensure_ascii=False),
                    "DEFAULT_BACKEND": backend,
                    "DEFAULT_MODE": mode,
                    "DEFAULT_PROFILE": profile,
                    "KB_HITS_JSON": json.dumps(hits, ensure_ascii=False),
                    "COMM_TRACE_JSON": json.dumps(blackboard.to_dict() if blackboard is not None else [], ensure_ascii=False),
                },
            ),
        )
        b = str(payload.get("backend", backend)).strip().lower()
        m = str(payload.get("mode", mode)).strip()
        p = str(payload.get("profile", profile)).strip()
        if b not in {"mp-spdz", "secretflow"}:
            b = backend
        return b, m or mode, p or profile


def _choose_backend(planner: PlannerOutput, probe: ProbeOutput) -> str:
    preferred = planner.constraints.get("preferred_backend")
    if preferred in {"mp-spdz", "secretflow"}:
        return preferred

    if probe.rtt_ms is not None and probe.rtt_ms > 80:
        return "secretflow"
    if probe.bandwidth_mbps is not None and probe.bandwidth_mbps < 20:
        return "mp-spdz"
    return "mp-spdz"


def _choose_mode(probe: ProbeOutput) -> str:
    if probe.rtt_ms is not None and probe.rtt_ms > 100:
        return "offline_precompute"
    return "online_balanced"


def _choose_parallelism(probe: ProbeOutput) -> int:
    cores = probe.cpu_cores or 2
    if cores <= 2:
        return 1
    if cores <= 8:
        return 2
    return 4


def _choose_profile(probe: ProbeOutput) -> str:
    if probe.bandwidth_mbps is not None and probe.bandwidth_mbps < 10:
        return "low_bandwidth"
    if probe.rtt_ms is not None and probe.rtt_ms > 120:
        return "high_latency"
    return "balanced"


def _apply_kb_hints(
    hits: list[dict[str, Any]],
    backend: str,
    mode: str,
    profile: str,
) -> tuple[str, str, str, list[str]]:
    notes: list[str] = []
    for hit in hits:
        rec = hit.get("recommendation", {})
        if isinstance(rec, dict):
            backend = str(rec.get("backend", backend))
            mode = str(rec.get("mode", mode))
            profile = str(rec.get("profile", profile))
        note = hit.get("note")
        if isinstance(note, str) and note:
            notes.append(f"KB: {note}")
    return backend, mode, profile, notes
