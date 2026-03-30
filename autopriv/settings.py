from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ModelSettings:
    api_key: str | None
    base_url: str | None
    model: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


@dataclass(slots=True)
class AppSettings:
    probe_interval_s: float = 300.0
    model_timeout_s: float = 30.0
    secretflow_env: str = "sf"
    secretflow_psi_script: str = "examples/psi/secretflow_psi_demo.py"
    model: ModelSettings | None = None


def load_settings() -> AppSettings:
    _load_dotenv()

    interval_raw = os.getenv("AUTOPRIV_PROBE_INTERVAL_S", "300")
    try:
        interval = max(float(interval_raw), 0.0)
    except ValueError:
        interval = 300.0

    timeout_raw = os.getenv("AUTOPRIV_LLM_TIMEOUT_S", "30")
    try:
        timeout_s = max(float(timeout_raw), 1.0)
    except ValueError:
        timeout_s = 30.0

    model_settings = ModelSettings(
        api_key=os.getenv("AUTOPRIV_LLM_API_KEY"),
        base_url=os.getenv("AUTOPRIV_LLM_BASE_URL"),
        model=os.getenv("AUTOPRIV_LLM_MODEL"),
    )
    secretflow_env = os.getenv("AUTOPRIV_SECRETFLOW_ENV", "sf").strip() or "sf"
    secretflow_psi_script = os.getenv("AUTOPRIV_SECRETFLOW_PSI_SCRIPT", "examples/psi/secretflow_psi_demo.py").strip()
    return AppSettings(
        probe_interval_s=interval,
        model_timeout_s=timeout_s,
        secretflow_env=secretflow_env,
        secretflow_psi_script=secretflow_psi_script,
        model=model_settings,
    )


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
