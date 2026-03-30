from __future__ import annotations

from dataclasses import asdict
from typing import Any

from autopriv.types import AgentMessage


class Blackboard:
    def __init__(self) -> None:
        self._messages: list[AgentMessage] = []

    def publish(self, sender: str, receiver: str, kind: str, content: dict[str, Any]) -> AgentMessage:
        msg = AgentMessage(sender=sender, receiver=receiver, kind=kind, content=content)
        self._messages.append(msg)
        return msg

    def list_messages(self) -> list[AgentMessage]:
        return list(self._messages)

    def to_dict(self) -> list[dict[str, Any]]:
        return [asdict(m) for m in self._messages]
