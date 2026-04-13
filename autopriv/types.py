from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class AgentMessage:
    sender: str
    receiver: str
    kind: str
    content: dict[str, Any] = field(default_factory=dict)
    ts_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class ProbePlan:
    objective: str = "collect runtime signals for backend selection"
    metrics: list[str] = field(default_factory=lambda: ["rtt_ms", "bandwidth_mbps", "cpu_cores", "memory_gb"])
    sample_count: int = 1
    interval_s: float = 300.0
    tool_args: dict[str, Any] = field(default_factory=dict)
    prober_prompt: str = "Collect network and host metrics for config optimization."


@dataclass(slots=True)
class PlannerOutput:
    instruction: str
    goals: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    requires_probe: bool = True
    request_execute: bool = False
    planning_notes: list[str] = field(default_factory=list)
    probe_plan: ProbePlan = field(default_factory=ProbePlan)
    planner_prompt: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ProbeOutput:
    ts_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bandwidth_mbps: float | None = None
    rtt_ms: float | None = None
    cpu_cores: int | None = None
    memory_gb: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProbeReport:
    sample_count: int
    interval_s: float
    samples: list[ProbeOutput] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    prober_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "interval_s": self.interval_s,
            "samples": [
                {
                    "ts_utc": s.ts_utc,
                    "bandwidth_mbps": s.bandwidth_mbps,
                    "rtt_ms": s.rtt_ms,
                    "cpu_cores": s.cpu_cores,
                    "memory_gb": s.memory_gb,
                    "raw": s.raw,
                }
                for s in self.samples
            ],
            "summary": self.summary,
            "policy": self.policy,
            "prober_prompt": self.prober_prompt,
        }


@dataclass(slots=True)
class ConfigOutput:
    backend: str
    mode: str
    parallelism: int
    profile: str
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "mode": self.mode,
            "parallelism": self.parallelism,
            "profile": self.profile,
            "notes": self.notes,
            "extra": self.extra,
        }


@dataclass(slots=True)
class CriticOutput:
    approved: bool
    decision: str = "reject"
    risk_level: str = "medium"
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    next_agent: str = "executor"

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "decision": self.decision,
            "risk_level": self.risk_level,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "next_agent": self.next_agent,
        }


@dataclass(slots=True)
class ExecutorOutput:
    backend: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass(slots=True)
class RunState:
    phase: str = "planning"
    status: str = "running"
    requires_probe: bool = True
    request_execute: bool = False
    probe_attempts: int = 0
    config_attempts: int = 0
    critic_attempts: int = 0
    critic_approved: bool = False
    executed: bool = False
    last_decision: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunContext:
    instruction: str
    planner: PlannerOutput | None = None
    probe: ProbeOutput | None = None
    probe_report: ProbeReport | None = None
    config: ConfigOutput | None = None
    critic: CriticOutput | None = None
    executor: ExecutorOutput | None = None
    state: RunState = field(default_factory=RunState)
