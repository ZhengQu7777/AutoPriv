from __future__ import annotations

import argparse
import json

from autopriv.orchestration.pipeline import AutoConfigPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AutoPriv multi-agent auto configuration")
    parser.add_argument("task", nargs="?", help="Task description for planning")
    parser.add_argument("--instruction", help="Deprecated alias of task")
    parser.add_argument("--out", default="examples/overall/overall_report.json", help="Output overall report path")
    parser.add_argument(
        "--config-out",
        default="examples/agents/configer/configer_output.json",
        help="Output config file path",
    )
    parser.add_argument(
        "--report-out",
        default="examples/agents/prober/prober_output.json",
        help="Output probe report path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    instruction = args.task or args.instruction
    if not instruction:
        raise SystemExit("Please provide a task. Example: python main.py \"configure private compute for low latency\"")

    pipeline = AutoConfigPipeline()
    data = pipeline.run_and_save(
        instruction=instruction,
        out_path=args.out,
        report_path=args.report_out,
        config_path=args.config_out,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
