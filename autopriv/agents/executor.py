from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from autopriv.agents.base import Agent
from autopriv.llm import LLMClient
from autopriv.orchestration.blackboard import Blackboard
from autopriv.prompting.prompt_store import load_prompt, render_prompt
from autopriv.settings import AppSettings, load_settings
from autopriv.types import ConfigOutput, ExecutorOutput, ProbeOutput, ProbeReport


BACKEND_GUIDE_FILES = {
    "mp-spdz": "executor_mp_spdz.txt",
}


class ExecutorAgent(Agent):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__(name="executor")
        self.settings = settings or load_settings()
        self.llm = LLMClient(self.settings)
        self._system_prompt = load_prompt("executor_system.txt")

    def run(
        self,
        config: ConfigOutput,
        instruction: str = "",
        probe: ProbeOutput | None = None,
        probe_report: ProbeReport | None = None,
        blackboard: Blackboard | None = None,
        **kwargs: Any,
    ) -> ExecutorOutput:
        backend = config.backend.lower().strip()
        guide_name = BACKEND_GUIDE_FILES.get(backend)

        if guide_name is None:
            out = ExecutorOutput(
                backend=backend,
                status="skipped",
                message=(
                    f"Backend '{backend}' is not supported in this round. "
                    "Only mp-spdz has an executor guide currently."
                ),
                details={"supported_backends": sorted(BACKEND_GUIDE_FILES.keys())},
            )
        else:
            try:
                out = self._generate_artifacts(
                    backend=backend,
                    guide_name=guide_name,
                    instruction=instruction,
                    config=config,
                    probe=probe,
                    probe_report=probe_report,
                )
            except Exception as exc:
                out = ExecutorOutput(
                    backend=backend,
                    status="error",
                    message="Executor failed to generate artifacts.",
                    details={"error": str(exc)},
                )

        if blackboard is not None:
            blackboard.publish(
                sender="executor",
                receiver="pipeline",
                kind="executor_output",
                content=out.to_dict(),
            )
        return out

    def _generate_artifacts(
        self,
        backend: str,
        guide_name: str,
        instruction: str,
        config: ConfigOutput,
        probe: ProbeOutput | None,
        probe_report: ProbeReport | None,
    ) -> ExecutorOutput:
        backend_guide = load_prompt(guide_name)

        probe_json = json.dumps(
            asdict(probe) if probe is not None else {},
            ensure_ascii=False,
        )
        probe_summary_json = json.dumps(
            probe_report.summary if probe_report is not None else {},
            ensure_ascii=False,
        )
        config_json = json.dumps(config.to_dict(), ensure_ascii=False)

        user_prompt = render_prompt(
            "executor_user.txt",
            {
                "INSTRUCTION": instruction or "(empty)",
                "CONFIG_JSON": config_json,
                "PROBE_JSON": probe_json,
                "PROBE_SUMMARY_JSON": probe_summary_json,
                "BACKEND_GUIDE": backend_guide,
            },
        )

        payload = self.llm.chat_json(
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
        )

        task_type = _safe_task_type(payload.get("task_type", ""))
        mpc_file = _extract_file(payload.get("mpc_file"), default_suffix=".mpc", fallback_name=f"{task_type}_task.mpc")
        sh_file = _extract_file(payload.get("sh_file"), default_suffix=".sh", fallback_name=f"run_{task_type}.sh")
        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            notes = [str(notes)]
        notes = [str(n).strip() for n in notes if str(n).strip()]

        output_root = _resolve_output_root(self.settings)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_dir = output_root / f"{timestamp}_{backend}_{task_type}"
        task_dir.mkdir(parents=True, exist_ok=True)

        mpc_path = task_dir / mpc_file["name"]
        sh_path = task_dir / sh_file["name"]
        mpc_path.write_text(mpc_file["content"], encoding="utf-8")
        sh_path.write_text(sh_file["content"], encoding="utf-8")
        try:
            sh_path.chmod(0o755)
        except OSError:
            pass

        (task_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "backend": backend,
                    "task_type": task_type,
                    "instruction": instruction,
                    "config": config.to_dict(),
                    "generated_files": [mpc_file["name"], sh_file["name"]],
                    "notes": notes,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        status = "generated" if task_type != "unsupported" else "skipped"
        message = (
            f"Generated {backend} {task_type} artifacts at {task_dir}"
            if status == "generated"
            else f"Backend {backend} task could not be resolved, see notes."
        )
        return ExecutorOutput(
            backend=backend,
            status=status,
            message=message,
            details={
                "task_type": task_type,
                "output_dir": str(task_dir),
                "mpc_file": str(mpc_path),
                "sh_file": str(sh_path),
                "notes": notes,
            },
        )


def _safe_task_type(raw: Any) -> str:
    token = str(raw or "").strip().lower()
    token = re.sub(r"[^a-z0-9_\-]+", "_", token).strip("_")
    return token or "task"


def _extract_file(raw: Any, default_suffix: str, fallback_name: str) -> dict[str, str]:
    name = ""
    content = ""
    if isinstance(raw, dict):
        name = str(raw.get("name", "")).strip()
        content = str(raw.get("content", ""))
    elif isinstance(raw, str):
        content = raw

    if not name:
        name = fallback_name
    if not name.endswith(default_suffix):
        name = f"{Path(name).stem}{default_suffix}"
    name = re.sub(r"[^A-Za-z0-9_.\-]+", "_", name)

    if not content.strip():
        content = (
            f"# placeholder {default_suffix} generated by AutoPriv executor\n"
            f"# LLM did not return usable content.\n"
        )
    return {"name": name, "content": content}


def _resolve_output_root(settings: AppSettings) -> Path:
    root_name = getattr(settings, "output_dir", None) or "output"
    root = Path(root_name)
    if not root.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        root = project_root / root
    root.mkdir(parents=True, exist_ok=True)
    return root
