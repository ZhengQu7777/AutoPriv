from __future__ import annotations

import json
import threading
from pathlib import Path

import pandas as pd
import spu
import spu.libspu.link as link


def _make_cfg(in_csv: Path, out_csv: Path, receiver_rank: int) -> spu.psi.PsiExecuteConfig:
    cfg = spu.psi.PsiExecuteConfig()

    cfg.input_params.path = str(in_csv)
    cfg.input_params.type = spu.psi.SourceType.SOURCE_TYPE_FILE_CSV
    cfg.input_params.selected_keys = ["id"]
    cfg.input_params.keys_unique = True

    cfg.output_params.path = str(out_csv)
    cfg.output_params.type = spu.psi.SourceType.SOURCE_TYPE_FILE_CSV
    cfg.output_params.disable_alignment = False

    cfg.protocol_conf.protocol = spu.psi.PsiProtocol.PROTOCOL_KKRT
    cfg.protocol_conf.receiver_rank = receiver_rank
    cfg.protocol_conf.broadcast_result = True

    return cfg


def main() -> None:
    out_dir = Path("examples/psi")
    out_dir.mkdir(parents=True, exist_ok=True)

    alice_in = out_dir / "alice_in.csv"
    bob_in = out_dir / "bob_in.csv"
    alice_out = out_dir / "alice_mem_psi.csv"
    bob_out = out_dir / "bob_mem_psi.csv"

    pd.DataFrame({"id": ["u1", "u2", "u3"], "alice_v": [1, 2, 3]}).to_csv(alice_in, index=False)
    pd.DataFrame({"id": ["u2", "u3", "u4"], "bob_v": [20, 30, 40]}).to_csv(bob_in, index=False)

    desc = link.Desc()
    desc.id = "mem-psi-demo"
    desc.add_party("alice", "thread_0")
    desc.add_party("bob", "thread_1")

    lctx0 = link.create_mem(desc, 0)
    lctx1 = link.create_mem(desc, 1)

    results: dict[str, str] = {}
    errors: dict[str, str] = {}

    def run_party(name: str, ctx: link.Context, in_csv: Path, out_csv: Path) -> None:
        try:
            cfg = _make_cfg(in_csv, out_csv, receiver_rank=0)
            report = spu.psi.psi_execute(cfg, ctx)
            results[name] = str(report)
        except Exception as exc:
            errors[name] = str(exc)

    t0 = threading.Thread(target=run_party, args=("alice", lctx0, alice_in, alice_out), daemon=True)
    t1 = threading.Thread(target=run_party, args=("bob", lctx1, bob_in, bob_out), daemon=True)

    t0.start()
    t1.start()
    t0.join()
    t1.join()

    if errors:
        raise RuntimeError(json.dumps(errors, ensure_ascii=False))

    alice_df = pd.read_csv(alice_out)
    bob_df = pd.read_csv(bob_out)

    summary = {
        "task": "spu_mem_psi",
        "intersection_ids": sorted(alice_df["id"].astype(str).tolist()),
        "alice_rows": int(len(alice_df)),
        "bob_rows": int(len(bob_df)),
        "reports": results,
        "outputs": {
            "alice": str(alice_out),
            "bob": str(bob_out),
        },
    }

    summary_path = out_dir / "spu_mem_psi_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
