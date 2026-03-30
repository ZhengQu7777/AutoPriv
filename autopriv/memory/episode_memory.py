from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any


class EpisodeMemory:
    def __init__(self, memory_path: str | Path = "examples/memory/episodes.jsonl") -> None:
        self.path = Path(memory_path)
        self.working: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self.working[key] = value

    def save_episode(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = _as_jsonable(self.working)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(serializable, ensure_ascii=False) + "\n")



def _as_jsonable(value: Any) -> Any:
    try:
        return asdict(value)
    except TypeError:
        pass

    if isinstance(value, dict):
        return {str(k): _as_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_as_jsonable(v) for v in value]
    return value
