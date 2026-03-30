from __future__ import annotations

import os
import socket
import time
import urllib.request
from statistics import mean
from typing import Any

from autopriv.tools.base import Tool


class NetworkProbeTool(Tool):
    name = "network_probe"

    def run(
        self,
        rtt_host: str = "8.8.8.8",
        rtt_port: int = 53,
        rtt_trials: int = 3,
        timeout_s: float = 1.5,
        bandwidth_url: str = "https://speed.hetzner.de/1MB.bin",
        max_bytes: int = 1024 * 1024,
    ) -> dict[str, Any]:
        rtt_values = []
        for _ in range(max(rtt_trials, 1)):
            start = time.perf_counter()
            try:
                with socket.create_connection((rtt_host, rtt_port), timeout=timeout_s):
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    rtt_values.append(elapsed_ms)
            except OSError:
                continue

        bandwidth_mbps = None
        try:
            req = urllib.request.Request(bandwidth_url, headers={"User-Agent": "autopriv-prober/0.1"})
            start = time.perf_counter()
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read(max_bytes)
            elapsed = max(time.perf_counter() - start, 1e-6)
            bandwidth_mbps = (len(data) * 8.0 / elapsed) / 1_000_000.0
        except OSError:
            bandwidth_mbps = None

        return {
            "rtt_ms": mean(rtt_values) if rtt_values else None,
            "bandwidth_mbps": bandwidth_mbps,
            "cpu_cores": os.cpu_count(),
            "memory_gb": _memory_gb(),
        }


def _memory_gb() -> float | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024**3)
    except (AttributeError, OSError, ValueError):
        return None
