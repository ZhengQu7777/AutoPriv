from __future__ import annotations

import time
from statistics import mean
from typing import Any

from autopriv.agents.base import Agent
from autopriv.orchestration.blackboard import Blackboard
from autopriv.tools.network import NetworkProbeTool
from autopriv.types import PlannerOutput, ProbeOutput, ProbeReport


class ProberAgent(Agent):
    def __init__(self) -> None:
        super().__init__(name="prober")
        self.tools.register(NetworkProbeTool())

    def run(self, **kwargs: Any) -> ProbeOutput:
        return self.run_once(**kwargs)

    def run_startup_snapshot(
        self,
        planner: PlannerOutput,
        periodic_interval_s: float = 300.0,
        blackboard: Blackboard | None = None,
        **kwargs: Any,
    ) -> ProbeReport:
        plan = planner.probe_plan
        # Keep startup probing responsive even if planner emits aggressive values.
        sample_count = min(max(plan.sample_count, 1), 3)
        interval_s = min(max(plan.interval_s, 0.0), 2.0)
        tool_args = plan.tool_args

        if sample_count <= 1:
            sample = self.run_once(**tool_args)
            samples = [sample]
        else:
            rep = self.run_periodic(sample_count=sample_count, interval_s=interval_s, **tool_args)
            samples = rep.samples

        summary = _build_summary(samples)
        policy = {
            "startup_probe": "run_once" if sample_count <= 1 else "run_periodic",
            "periodic_probe_interval_s": max(periodic_interval_s, 0.0),
            "note": "Designed for long-running executor to re-probe periodically.",
        }
        report = ProbeReport(
            sample_count=len(samples),
            interval_s=max(periodic_interval_s, 0.0),
            samples=samples,
            summary=summary,
            policy=policy,
            prober_prompt=plan.prober_prompt,
        )
        if blackboard is not None:
            blackboard.publish(
                sender="prober",
                receiver="configer",
                kind="probe_report",
                content=report.to_dict(),
            )
        return report

    def run_once(self, **kwargs: Any) -> ProbeOutput:
        data = self.tools.call("network_probe")
        return ProbeOutput(
            bandwidth_mbps=_to_float(data.get("bandwidth_mbps")),
            rtt_ms=_to_float(data.get("rtt_ms")),
            cpu_cores=_to_int(data.get("cpu_cores")),
            memory_gb=_to_float(data.get("memory_gb")),
            raw=data,
        )

    def run_periodic(self, sample_count: int = 3, interval_s: float = 5.0, **kwargs: Any) -> ProbeReport:
        n = max(sample_count, 1)
        samples: list[ProbeOutput] = []
        for i in range(n):
            samples.append(self.run_once(**kwargs))
            if i != n - 1 and interval_s > 0:
                time.sleep(interval_s)

        summary = _build_summary(samples)
        policy = {
            "startup_probe": "run_periodic",
            "periodic_probe_interval_s": max(interval_s, 0.0),
        }
        return ProbeReport(
            sample_count=n,
            interval_s=max(interval_s, 0.0),
            samples=samples,
            summary=summary,
            policy=policy,
        )


def _to_float(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _build_summary(samples: list[ProbeOutput]) -> dict[str, Any]:
    def avg(items: list[float | None]) -> float | None:
        vals = [v for v in items if v is not None]
        return mean(vals) if vals else None

    rtts = [s.rtt_ms for s in samples]
    bws = [s.bandwidth_mbps for s in samples]
    cpus = [s.cpu_cores for s in samples]
    mems = [s.memory_gb for s in samples]

    return {
        "avg_rtt_ms": avg(rtts),
        "avg_bandwidth_mbps": avg(bws),
        "max_rtt_ms": max((v for v in rtts if v is not None), default=None),
        "min_bandwidth_mbps": min((v for v in bws if v is not None), default=None),
        "cpu_cores": max((v for v in cpus if v is not None), default=None),
        "memory_gb": max((v for v in mems if v is not None), default=None),
    }
