"""CodeGuard CLI — 命令行入口。

用法:
    python cli.py --task "修复 bug" --workspace ./project --mock
"""

import argparse
import sys

from src.agent import run
from src.llm_client import MockLLM, RealLLM
from src.parser import parse_llm_output
from src.guardrail import evaluate
import src.tools as tools


def main():
    parser = argparse.ArgumentParser(
        prog="codeguard",
        description="CodeGuard — AI coding agent with governance guardrails",
    )
    parser.add_argument(
        "--task", required=True, help="Task description for the agent"
    )
    parser.add_argument(
        "--workspace", default=".", help="Workspace directory (default: .)"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use MockLLM instead of real API"
    )
    args = parser.parse_args()

    if args.mock:
        llm = MockLLM([])
    else:
        llm = RealLLM()

    result = run(
        args.task,
        args.workspace,
        llm_client=llm,
        parse_fn=parse_llm_output,
        evaluate_fn=evaluate,
        tools_module=tools,
    )

    print(f"Done. Steps: {result['steps']}, Finish reason: {result['finish_reason']}")


if __name__ == "__main__":
    main()