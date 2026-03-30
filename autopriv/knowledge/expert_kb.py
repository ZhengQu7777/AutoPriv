from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autopriv.types import PlannerOutput, ProbeOutput


class ExpertKnowledgeBase:
    def __init__(self, kb_path: str | Path | None = None) -> None:
        default_path = Path(__file__).with_name("expert_rules.json")
        self.kb_path = Path(kb_path) if kb_path else default_path
        self.rules = self._load_rules(self.kb_path)

    def retrieve(self, planner: PlannerOutput, probe: ProbeOutput, top_k: int = 3) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        for rule in self.rules:
            when = rule.get("when", {})
            if _matches(when, planner, probe):
                matched.append(rule)
            if len(matched) >= max(top_k, 1):
                break
        return matched

    @staticmethod
    def _load_rules(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data.get("rules", [])
        if isinstance(rules, list):
            return [r for r in rules if isinstance(r, dict)]
        return []


def _matches(when: dict[str, Any], planner: PlannerOutput, probe: ProbeOutput) -> bool:
    preferred_backend = planner.constraints.get("preferred_backend")
    priority = planner.constraints.get("priority")

    min_rtt = when.get("min_rtt_ms")
    max_rtt = when.get("max_rtt_ms")
    min_bw = when.get("min_bandwidth_mbps")
    max_bw = when.get("max_bandwidth_mbps")

    if "preferred_backend" in when and when["preferred_backend"] != preferred_backend:
        return False
    if "priority" in when and when["priority"] != priority:
        return False
    if min_rtt is not None and (probe.rtt_ms is None or probe.rtt_ms < float(min_rtt)):
        return False
    if max_rtt is not None and (probe.rtt_ms is None or probe.rtt_ms > float(max_rtt)):
        return False
    if min_bw is not None and (probe.bandwidth_mbps is None or probe.bandwidth_mbps < float(min_bw)):
        return False
    if max_bw is not None and (probe.bandwidth_mbps is None or probe.bandwidth_mbps > float(max_bw)):
        return False

    return True
