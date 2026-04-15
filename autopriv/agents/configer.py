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
from autopriv.types import ConfigOutput, CriticOutput, PlannerOutput, ProbeOutput


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
        prev_config: ConfigOutput | None = None,
        critic_feedback: CriticOutput | None = None,
        **kwargs: Any,
    ) -> ConfigOutput:
        defaults = {
            "backend": _choose_backend(planner, probe),
            "mode": _choose_mode(probe),
            "parallelism": _choose_parallelism(probe),
            "profile": _choose_profile(probe),
        }

        hits = self.kb.retrieve(planner=planner, probe=probe)
        defaults, kb_notes = _apply_kb_hints(hits, defaults)

        refined = self._llm_refine(
            planner=planner,
            probe=probe,
            defaults=defaults,
            kb_notes=kb_notes,
            hits=hits,
            blackboard=blackboard,
            prev_config=prev_config,
            critic_feedback=critic_feedback,
        )

        backend = refined["backend"]
        mode = refined["mode"]
        parallelism = refined["parallelism"]
        profile = refined["profile"]
        notes = refined["notes"]

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
        defaults: dict[str, Any],
        kb_notes: list[str],
        hits: list[dict[str, Any]],
        blackboard: Blackboard | None,
        prev_config: ConfigOutput | None,
        critic_feedback: CriticOutput | None,
    ) -> dict[str, Any]:
        variables: dict[str, str] = {
            "PLANNER_JSON": json.dumps(asdict(planner), ensure_ascii=False),
            "PROBE_JSON": json.dumps(asdict(probe), ensure_ascii=False),
            "DEFAULTS_JSON": json.dumps(defaults, ensure_ascii=False),
            "KB_NOTES_JSON": json.dumps(kb_notes, ensure_ascii=False),
            "KB_HITS_JSON": json.dumps(hits, ensure_ascii=False),
            "COMM_TRACE_JSON": json.dumps(
                blackboard.to_dict() if blackboard is not None else [],
                ensure_ascii=False,
            ),
            "PREV_CONFIG_JSON": json.dumps(
                prev_config.to_dict() if prev_config is not None else None,
                ensure_ascii=False,
            ),
            "CRITIC_FEEDBACK_JSON": json.dumps(
                critic_feedback.to_dict() if critic_feedback is not None else None,
                ensure_ascii=False,
            ),
        }

        payload = self.llm.chat_json(
            system_prompt=render_prompt("configer_system.txt"),
            user_prompt=render_prompt("configer_user.txt", variables),
        )

        backend = str(payload.get("backend", defaults["backend"])).strip().lower()
        if backend not in {"mp-spdz", "secretflow"}:
            backend = defaults["backend"]

        mode = str(payload.get("mode", defaults["mode"])).strip()
        if not mode:
            mode = defaults["mode"]

        profile = str(payload.get("profile", defaults["profile"])).strip()
        if not profile:
            profile = defaults["profile"]

        parallelism = payload.get("parallelism", defaults["parallelism"])
        try:
            parallelism = max(int(parallelism), 1)
        except (TypeError, ValueError):
            parallelism = defaults["parallelism"]

        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            notes = [str(notes)]
        notes = [str(n).strip() for n in notes if str(n).strip()]
        if not notes:
            notes = kb_notes[:]

        return {
            "backend": backend,
            "mode": mode,
            "parallelism": parallelism,
            "profile": profile,
            "notes": notes,
        }


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
    defaults: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    for hit in hits:
        rec = hit.get("recommendation", {})
        if isinstance(rec, dict):
            if "backend" in rec:
                defaults["backend"] = str(rec["backend"])
            if "mode" in rec:
                defaults["mode"] = str(rec["mode"])
            if "profile" in rec:
                defaults["profile"] = str(rec["profile"])
        note = hit.get("note")
        if isinstance(note, str) and note:
            notes.append(f"KB: {note}")
    return defaults, notes
