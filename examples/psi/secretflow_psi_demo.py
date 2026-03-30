from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import secretflow as sf


def _local_cluster_def() -> dict:
    # Use fixed localhost ports with retry policy to avoid occasional local mesh race failures.
    return {
        "nodes": [
            {"party": "alice", "address": "127.0.0.1:9301"},
            {"party": "bob", "address": "127.0.0.1:9302"},
        ],
        "runtime_config": {
            "protocol": "SEMI2K",
            "field": "FM128",
        },
        "link_desc": {
            "connect_retry_times": 120,
            "connect_retry_interval_ms": 500,
            "recv_timeout_ms": 300000,
            "http_timeout_ms": 300000,
        },
    }


def main() -> None:
    sf.shutdown()
    sf.init(["alice", "bob"], address="local", debug_mode=True)

    alice = sf.PYU("alice")
    bob = sf.PYU("bob")
    spu = sf.SPU(_local_cluster_def())

    alice_df = alice(lambda: pd.DataFrame({"id": ["u1", "u2", "u3"], "alice_v": [1, 2, 3]}))()
    bob_df = bob(lambda: pd.DataFrame({"id": ["u2", "u3", "u4"], "bob_v": [20, 30, 40]}))()

    result = spu.psi_df(
        key="id",
        dfs=[alice_df, bob_df],
        receiver="alice",
        protocol="PROTOCOL_RR22",
        broadcast_result=True,
    )

    revealed = sf.reveal(result)

    out_dir = Path("examples/psi")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = []
    if isinstance(revealed, list):
        for idx, item in enumerate(revealed):
            if isinstance(item, pd.DataFrame):
                csv_path = out_dir / f"psi_result_party_{idx}.csv"
                item.to_csv(csv_path, index=False)
                payload.append({"party_index": idx, "rows": len(item), "columns": list(item.columns)})
            else:
                payload.append({"party_index": idx, "type": str(type(item))})
    else:
        payload.append({"type": str(type(revealed))})

    summary = {
        "task": "secretflow_psi_df_demo",
        "receiver": "alice",
        "result": payload,
    }
    (out_dir / "psi_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sf.shutdown()


if __name__ == "__main__":
    main()
