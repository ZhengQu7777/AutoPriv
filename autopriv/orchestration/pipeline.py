from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from autopriv.agents.configer import ConfigerAgent
from autopriv.agents.critic import CriticAgent
from autopriv.agents.executor import ExecutorAgent
from autopriv.agents.planner import PlannerAgent
from autopriv.agents.prober import ProberAgent
from autopriv.llm import LLMClient
from autopriv.orchestration.blackboard import Blackboard
from autopriv.settings import AppSettings, load_settings
from autopriv.types import (
    ConfigOutput,
    CriticOutput,
    ExecutorOutput,
    PlannerOutput,
    ProbeOutput,
    ProbeReport,
    RunContext,
    RunState,
)

logger = logging.getLogger(__name__)

MAX_PROBE_RETRIES = 2
MAX_CONFIG_REVIEW_CYCLES = 3


class AutoConfigPipeline:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()
        LLMClient(self.settings).ensure_ready()
        self.planner = PlannerAgent(settings=self.settings)
        self.prober = ProberAgent()
        self.configer = ConfigerAgent(settings=self.settings)
        self.critic = CriticAgent(settings=self.settings)
        self.executor = ExecutorAgent(settings=self.settings)

    def run(self, instruction: str) -> dict[str, Any]:
        return self._run_core(instruction=instruction)

    # ── phase‑based pipeline ─────────────────────────────────────
    def _run_core(self, instruction: str) -> dict[str, Any]:
        board = Blackboard()
        ctx = RunContext(instruction=instruction)

        self._run_plan_phase(ctx, board)
        if ctx.state.requires_probe:
            self._run_probe_phase(ctx, board)
        self._run_config_review_phase(ctx, board)
        if ctx.state.request_execute and ctx.state.critic_approved:
            self._run_executor_phase(ctx, board)

        ctx.state.status = "done"
        return self._build_result(ctx, board)

    # ── plan phase ───────────────────────────────────────────────
    def _run_plan_phase(self, ctx: RunContext, board: Blackboard) -> None:
        ctx.state.phase = "planning"
        planner_out = self.planner.run(instruction=ctx.instruction, blackboard=board)
        ctx.planner = planner_out
        ctx.state.requires_probe = planner_out.requires_probe
        ctx.state.request_execute = planner_out.request_execute
        logger.info("plan_phase done: requires_probe=%s request_execute=%s",
                     ctx.state.requires_probe, ctx.state.request_execute)

    # ── probe phase ──────────────────────────────────────────────
    def _run_probe_phase(self, ctx: RunContext, board: Blackboard) -> None:
        ctx.state.phase = "probing"
        assert ctx.planner is not None
        for attempt in range(1, MAX_PROBE_RETRIES + 1):
            ctx.state.probe_attempts = attempt
            report = self.prober.run_startup_snapshot(
                planner=ctx.planner,
                periodic_interval_s=self.settings.probe_interval_s,
                blackboard=board,
            )
            ctx.probe_report = report
            ctx.probe = report.samples[-1] if report.samples else None
            if not _probe_anomaly(report):
                logger.info("probe_phase ok at attempt %d", attempt)
                return
            logger.warning("probe_phase anomaly at attempt %d", attempt)
        logger.warning("probe_phase: proceeding despite anomaly after %d attempts", MAX_PROBE_RETRIES)

    # ── config + review cycle ────────────────────────────────────
    def _run_config_review_phase(self, ctx: RunContext, board: Blackboard) -> None:
        assert ctx.planner is not None
        if ctx.probe is None and ctx.state.requires_probe:
            self._run_probe_phase(ctx, board)

        for cycle in range(1, MAX_CONFIG_REVIEW_CYCLES + 1):
            ctx.state.phase = "configuring"
            ctx.state.config_attempts = cycle
            assert ctx.probe is not None or not ctx.state.requires_probe
            probe_for_config = ctx.probe
            if probe_for_config is None:
                probe_for_config = ProbeOutput()
            prev_config = ctx.config if cycle > 1 else None
            critic_feedback = ctx.critic if cycle > 1 else None
            ctx.config = self.configer.run(
                planner=ctx.planner,
                probe=probe_for_config,
                blackboard=board,
                prev_config=prev_config,
                critic_feedback=critic_feedback,
            )

            ctx.state.phase = "reviewing"
            ctx.state.critic_attempts += 1
            assert ctx.probe_report is not None or not ctx.state.requires_probe
            probe_report_for_critic = ctx.probe_report
            if probe_report_for_critic is None:
                probe_report_for_critic = ProbeReport(sample_count=0, interval_s=0.0)
            ctx.critic = self.critic.run(
                planner=ctx.planner,
                probe_report=probe_report_for_critic,
                config=ctx.config,
                blackboard=board,
            )

            decision = ctx.critic.decision
            ctx.state.last_decision = decision
            ctx.state.critic_approved = ctx.critic.approved

            if decision == "approve":
                logger.info("config_review_phase approved at cycle %d", cycle)
                return
            if decision == "re_probe":
                logger.info("config_review_phase: critic requested re_probe at cycle %d", cycle)
                self._run_probe_phase(ctx, board)
                continue
            if decision == "re_config":
                logger.info("config_review_phase: critic requested re_config at cycle %d", cycle)
                continue
            logger.warning("config_review_phase: critic rejected at cycle %d", cycle)
            return

        logger.warning("config_review_phase: max cycles reached, using last result")

    # ── executor phase ───────────────────────────────────────────
    def _run_executor_phase(self, ctx: RunContext, board: Blackboard) -> None:
        ctx.state.phase = "executing"
        assert ctx.config is not None
        ctx.executor = self.executor.run(config=ctx.config, blackboard=board)
        ctx.state.executed = True
        logger.info("executor_phase done: status=%s", ctx.executor.status)

    # ── build final result dict ──────────────────────────────────
    @staticmethod
    def _build_result(ctx: RunContext, board: Blackboard) -> dict[str, Any]:
        return {
            "planner": asdict(ctx.planner) if ctx.planner else {},
            "prober": asdict(ctx.probe) if ctx.probe else {},
            "probe_report": ctx.probe_report.to_dict() if ctx.probe_report else {},
            "config": ctx.config.to_dict() if ctx.config else {},
            "critic": ctx.critic.to_dict() if ctx.critic else {},
            "executor": ctx.executor.to_dict() if ctx.executor else None,
            "state": ctx.state.to_dict(),
            "messages": board.to_dict(),
        }

    # ── run and save ─────────────────────────────────────────────
    def run_and_save(
        self,
        instruction: str,
        out_path: str | Path,
        report_path: str | Path | None = None,
        config_path: str | Path | None = None,
    ) -> dict[str, Any]:
        data = self.run(instruction=instruction)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        self._write_readable_reports(base_dir=out.parent, data=data)

        if report_path is not None:
            rp = Path(report_path)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(data["probe_report"], ensure_ascii=False, indent=2), encoding="utf-8")

        if config_path is not None:
            cp = Path(config_path)
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(data["config"], ensure_ascii=False, indent=2), encoding="utf-8")

        return data

    @staticmethod
    def _write_readable_reports(base_dir: Path, data: dict[str, Any]) -> None:
        agents_dir = base_dir / "agents"
        overall_dir = base_dir / "overall"
        planner_dir = agents_dir / "planner"
        prober_dir = agents_dir / "prober"
        configer_dir = agents_dir / "configer"
        critic_dir = agents_dir / "critic"
        executor_dir = agents_dir / "executor"

        for d in [planner_dir, prober_dir, configer_dir, critic_dir, executor_dir, overall_dir]:
            d.mkdir(parents=True, exist_ok=True)

        (planner_dir / "planner_output.json").write_text(
            json.dumps(data.get("planner", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (prober_dir / "prober_output.json").write_text(
            json.dumps(
                {
                    "prober": data.get("prober", {}),
                    "probe_report": data.get("probe_report", {}),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (configer_dir / "configer_output.json").write_text(
            json.dumps(data.get("config", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (critic_dir / "critic_output.json").write_text(
            json.dumps(data.get("critic", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (executor_dir / "executor_output.json").write_text(
            json.dumps(data.get("executor", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (overall_dir / "overall_report.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        planner = data.get("planner", {})
        prober = data.get("prober", {})
        probe_report = data.get("probe_report", {})
        config = data.get("config", {})
        critic = data.get("critic", {})
        executor = data.get("executor", {}) or {}
        state = data.get("state", {})

        texts = {
            planner_dir / "planner_output.txt": "\n".join(
                [
                    "[Planner]",
                    f"instruction: {planner.get('instruction')}",
                    f"goals: {planner.get('goals')}",
                    f"constraints: {planner.get('constraints')}",
                    f"requires_probe: {planner.get('requires_probe')}",
                    f"request_execute: {planner.get('request_execute')}",
                    f"probe_plan: {planner.get('probe_plan')}",
                ]
            ),
            prober_dir / "prober_output.txt": "\n".join(
                [
                    "[Prober]",
                    f"latest_sample: {prober}",
                    f"summary: {probe_report.get('summary')}",
                    f"policy: {probe_report.get('policy')}",
                    f"prompt: {probe_report.get('prober_prompt')}",
                ]
            ),
            configer_dir / "configer_output.txt": "\n".join(
                [
                    "[Configer]",
                    f"backend: {config.get('backend')}",
                    f"mode: {config.get('mode')}",
                    f"parallelism: {config.get('parallelism')}",
                    f"profile: {config.get('profile')}",
                    f"notes: {config.get('notes')}",
                ]
            ),
            critic_dir / "critic_output.txt": "\n".join(
                [
                    "[Critic]",
                    f"approved: {critic.get('approved')}",
                    f"decision: {critic.get('decision')}",
                    f"risk_level: {critic.get('risk_level')}",
                    f"issues: {critic.get('issues')}",
                    f"recommendations: {critic.get('recommendations')}",
                    f"next_agent: {critic.get('next_agent')}",
                ]
            ),
            executor_dir / "executor_output.txt": "\n".join(
                [
                    "[Executor]",
                    f"backend: {executor.get('backend')}",
                    f"status: {executor.get('status')}",
                    f"message: {executor.get('message')}",
                    f"details: {executor.get('details')}",
                ]
            ),
            overall_dir / "overall_report.txt": "\n".join(
                [
                    "[Overall]",
                    f"state: {state}",
                    f"final_backend: {config.get('backend')}",
                    f"final_mode: {config.get('mode')}",
                    f"final_profile: {config.get('profile')}",
                    f"critic_approved: {critic.get('approved')}",
                    f"critic_decision: {critic.get('decision')}",
                ]
            ),
        }
        for path, content in texts.items():
            path.write_text(content + "\n", encoding="utf-8")


def _probe_anomaly(report: ProbeReport) -> bool:
    max_rtt = report.summary.get("max_rtt_ms")
    min_bw = report.summary.get("min_bandwidth_mbps")

    if isinstance(max_rtt, (int, float)) and max_rtt > 350:
        return True
    if min_bw is None:
        return True
    if isinstance(min_bw, (int, float)) and min_bw < 5:
        return True
    return False
