from __future__ import annotations

import json
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
from autopriv.types import ConfigOutput, CriticOutput, ExecutorOutput, PlannerOutput, ProbeOutput, ProbeReport


class AutoConfigPipeline:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()
        LLMClient(self.settings).ensure_ready()
        self.planner = PlannerAgent(settings=self.settings)
        self.prober = ProberAgent()
        self.configer = ConfigerAgent(settings=self.settings)
        self.critic = CriticAgent(settings=self.settings)
        self.executor = ExecutorAgent(settings=self.settings)

#这两个函数一模一样
    def run(self, instruction: str) -> dict[str, Any]:
        return self._run_core(instruction=instruction)

    def run_with_probe_policy(self, instruction: str) -> dict[str, Any]:
        return self._run_core(instruction=instruction)

    def _run_core(self, instruction: str) -> dict[str, Any]:
        board = Blackboard()
        planner_out = self.planner.run(instruction=instruction, blackboard=board)

        probe_report: ProbeReport | None = None
        probe_out: ProbeOutput | None = None
        config_out: ConfigOutput | None = None
        critic_out: CriticOutput | None = None
        executor_out: ExecutorOutput | None = None
        observation: dict[str, Any] = {}
        action_trace: list[dict[str, Any]] = []

        state = {
            "has_probe": False,
            "has_config": False,
            "has_critic": False,
            "critic_approved": False,
            "has_executor": False,
            "replan_count": 0,
        }

        max_steps = 8
        for _ in range(max_steps):
            action = self.planner.decide_next(
                instruction=instruction,
                state=state,
                observation=observation,
                blackboard=board,
            )
            action_trace.append(asdict(action))

            # Allow planner to adjust probe strategy incrementally.
            if action.updates:
                self._apply_planner_updates(planner_out, action.updates)

            if action.done or action.agent == "stop":
                break

            if action.agent == "prober":
                probe_report = self.prober.run_startup_snapshot(
                    planner=planner_out,
                    periodic_interval_s=self.settings.probe_interval_s,
                    blackboard=board,
                )
                #这里拿到的是最新结果，是否考虑拿到的是平均结果？
                probe_out = probe_report.samples[-1]
                state["has_probe"] = True
                anomaly = _probe_anomaly(probe_report)
                observation = {
                    "from": "prober",
                    "anomaly_detected": anomaly,
                    "probe_summary": probe_report.summary,
                }
                if anomaly:
                    state["replan_count"] = int(state["replan_count"]) + 1
                continue

            if action.agent == "configer":
                if probe_out is None:
                    observation = {"from": "pipeline", "error": "missing_probe_before_config"}
                    continue
                config_out = self.configer.run(planner=planner_out, probe=probe_out, blackboard=board)
                state["has_config"] = True
                observation = {
                    "from": "configer",
                    "backend": config_out.backend,
                    "mode": config_out.mode,
                    "profile": config_out.profile,
                }
                continue

            if action.agent == "critic":
                if config_out is None or probe_report is None:
                    observation = {"from": "pipeline", "error": "missing_config_or_probe_before_critic"}
                    continue
                critic_out = self.critic.run(
                    planner=planner_out,
                    probe_report=probe_report,
                    config=config_out,
                    blackboard=board,
                )
                state["has_critic"] = True
                state["critic_approved"] = critic_out.approved
                observation = {
                    "from": "critic",
                    "approved": critic_out.approved,
                    "risk_level": critic_out.risk_level,
                    "issues": critic_out.issues,
                    "next_agent": critic_out.next_agent,
                }
                if critic_out.approved:
                    break
                continue

            if action.agent == "executor":
                if config_out is None:
                    observation = {"from": "pipeline", "error": "missing_config_before_executor"}
                    continue
                if critic_out is None or not critic_out.approved:
                    observation = {"from": "pipeline", "error": "critic_not_approved"}
                    continue
                executor_out = self.executor.run(config=config_out, blackboard=board)
                state["has_executor"] = True
                observation = {
                    "from": "executor",
                    "status": executor_out.status,
                    "backend": executor_out.backend,
                    "message": executor_out.message,
                }
                break
                continue

            observation = {"from": "pipeline", "warning": f"unknown agent: {action.agent}"}

        # Safety fallback to ensure outputs exist.
        if probe_report is None:
            probe_report = self.prober.run_startup_snapshot(
                planner=planner_out,
                periodic_interval_s=self.settings.probe_interval_s,
                blackboard=board,
            )
            probe_out = probe_report.samples[-1]
            state["has_probe"] = True

        if config_out is None:
            assert probe_out is not None
            config_out = self.configer.run(planner=planner_out, probe=probe_out, blackboard=board)
            state["has_config"] = True

        if critic_out is None:
            critic_out = self.critic.run(
                planner=planner_out,
                probe_report=probe_report,
                config=config_out,
                blackboard=board,
            )
            state["has_critic"] = True
            state["critic_approved"] = critic_out.approved

        assert probe_out is not None
        return {
            "planner": asdict(planner_out),
            "prober": asdict(probe_out),
            "probe_report": probe_report.to_dict(),
            "config": config_out.to_dict(),
            "critic": critic_out.to_dict(),
            "executor": executor_out.to_dict() if executor_out is not None else None,
            "state": state,
            "actions": action_trace,
            "messages": board.to_dict(),
        }

    def run_and_save(
        self,
        instruction: str,
        out_path: str | Path,
        report_path: str | Path | None = None,
        config_path: str | Path | None = None,
    ) -> dict[str, Any]:
        data = self.run_with_probe_policy(instruction=instruction)
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
        actions = data.get("actions", [])

        texts = {
            planner_dir / "planner_output.txt": "\n".join(
                [
                    "[Planner]",
                    f"instruction: {planner.get('instruction')}",
                    f"goals: {planner.get('goals')}",
                    f"constraints: {planner.get('constraints')}",
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
                    f"action_count: {len(actions)}",
                    f"final_backend: {config.get('backend')}",
                    f"final_mode: {config.get('mode')}",
                    f"final_profile: {config.get('profile')}",
                    f"critic_approved: {critic.get('approved')}",
                ]
            ),
        }
        for path, content in texts.items():
            path.write_text(content + "\n", encoding="utf-8")

    @staticmethod
    def _apply_planner_updates(planner_out: PlannerOutput, updates: dict[str, Any]) -> None:
        probe_updates = updates.get("probe_plan", updates)
        if not isinstance(probe_updates, dict):
            return

        if "sample_count" in probe_updates:
            try:
                planner_out.probe_plan.sample_count = max(int(probe_updates["sample_count"]), 1)
            except (TypeError, ValueError):
                pass
        if "interval_s" in probe_updates:
            try:
                planner_out.probe_plan.interval_s = max(float(probe_updates["interval_s"]), 0.0)
            except (TypeError, ValueError):
                pass
        if "prober_prompt" in probe_updates and isinstance(probe_updates["prober_prompt"], str):
            planner_out.probe_plan.prober_prompt = probe_updates["prober_prompt"]



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
