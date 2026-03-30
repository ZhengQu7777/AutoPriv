from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from autopriv.tools.base import ToolRegistry


class Agent(ABC):
    def __init__(self, name: str, tools: ToolRegistry | None = None) -> None:
        self.name = name
        self.tools = tools or ToolRegistry()

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        raise NotImplementedError
