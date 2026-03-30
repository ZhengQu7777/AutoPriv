from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from autopriv.agents.base import Agent
from autopriv.orchestration.blackboard import Blackboard
from autopriv.settings import AppSettings, load_settings
from autopriv.types import ConfigOutput, ExecutorOutput


class ExecutorAgent(Agent):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__(name="executor")
        self.settings = settings or load_settings()

    def run(
        self,
        config: ConfigOutput,
        blackboard: Blackboard | None = None,
        **kwargs: Any,
    ) -> ExecutorOutput:
        backend = config.backend.lower().strip()
        if backend == "secretflow":
            out = self._run_secretflow()
        elif backend == "mp-spdz":
            out = self._run_mpspdz()
        else:
            out = ExecutorOutput(
                backend=backend,
                status="error",
                message=f"Unsupported backend: {backend}",
                details={},
            )

        if blackboard is not None:
            blackboard.publish(
                sender="executor",
                receiver="pipeline",
                kind="executor_output",
                content=out.to_dict(),
            )
        return out

    def _run_secretflow(self) -> ExecutorOutput:
        project_root = Path(__file__).resolve().parents[2]
        script_path = project_root / self.settings.secretflow_psi_script
        if not script_path.exists():
            return ExecutorOutput(
                backend="secretflow",
                status="error",
                message="SecretFlow PSI script not found.",
                details={"script": str(script_path)},
            )

        cmd = [
            "conda",
            "run",
            "-n",
            self.settings.secretflow_env,
            "python",
            str(script_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            if proc.returncode == 0:
                return ExecutorOutput(
                    backend="secretflow",
                    status="ok",
                    message="SecretFlow PSI task executed.",
                    details={
                        "env": self.settings.secretflow_env,
                        "script": str(script_path),
                        "stdout_tail": _tail(proc.stdout, 50),
                    },
                )
            return ExecutorOutput(
                backend="secretflow",
                status="error",
                message="SecretFlow PSI task failed.",
                details={
                    "env": self.settings.secretflow_env,
                    "script": str(script_path),
                    "returncode": proc.returncode,
                    "stderr_tail": _tail(proc.stderr, 80),
                    "stdout_tail": _tail(proc.stdout, 30),
                },
            )
        except Exception as exc:
            return ExecutorOutput(
                backend="secretflow",
                status="error",
                message="SecretFlow execution failed unexpectedly.",
                details={"error": str(exc)},
            )

    @staticmethod
    def _run_mpspdz() -> ExecutorOutput:
        # MP-SPDZ runtime wiring is repository-specific and left as adapter work.
        return ExecutorOutput(
            backend="mp-spdz",
            status="todo",
            message="MP-SPDZ adapter is not implemented yet.",
            details={},
        )


def _tail(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])
