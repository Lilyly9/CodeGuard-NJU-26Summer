"""CodeGuard CLI — 命令行入口。

用法:
    python cli.py setup        # 引导用户输入 API Key 保存到 keyring
    python cli.py status       # 显示是否已配置（不显示明文）
    python cli.py clear        # 从 keyring 删除 key
    python cli.py run --task "修复 bug" --workspace ./project --mock
"""

import argparse
import getpass
import sys

from src.agent import run
from src.llm_client import MockLLM, RealLLM
from src.parser import parse_llm_output
from src.guardrail import evaluate
import src.tools as tools


def cmd_setup(_args):
    from src.keyring_manager import KeyringManager
    km = KeyringManager()
    print("Enter your OpenAI API Key (input will be hidden):")
    api_key = getpass("API Key: ").strip()
    if not api_key:
        print("Error: API Key cannot be empty.")
        sys.exit(1)
    km.set_key(api_key)
    print("API Key saved to system keyring.")


def cmd_status(_args):
    from src.keyring_manager import KeyringManager
    km = KeyringManager()
    if km.is_configured():
        print("Status: Configured (API Key is stored in system keyring)")
    else:
        print("Status: Not configured. Run 'python cli.py setup' to configure.")


def cmd_clear(_args):
    from src.keyring_manager import KeyringManager
    km = KeyringManager()
    km.delete_key()
    print("API Key removed from system keyring.")


def cmd_run(args):
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


def main():
    parser = argparse.ArgumentParser(
        prog="codeguard",
        description="CodeGuard — AI coding agent with governance guardrails",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    parser_setup = subparsers.add_parser("setup", help="Save API Key to system keyring")
    parser_setup.set_defaults(func=cmd_setup)

    parser_status = subparsers.add_parser("status", help="Show keyring configuration status")
    parser_status.set_defaults(func=cmd_status)

    parser_clear = subparsers.add_parser("clear", help="Remove API Key from system keyring")
    parser_clear.set_defaults(func=cmd_clear)

    parser_run = subparsers.add_parser("run", help="Run the agent")
    parser_run.add_argument("--task", required=True, help="Task description for the agent")
    parser_run.add_argument("--workspace", default=".", help="Workspace directory (default: .)")
    parser_run.add_argument("--mock", action="store_true", help="Use MockLLM instead of real API")
    parser_run.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()