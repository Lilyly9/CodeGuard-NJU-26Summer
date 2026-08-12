"""CodeGuard CLI — 命令行入口。

用法:
    python cli.py setup        # 引导用户输入 API Key 保存到 keyring
    python cli.py status       # 显示是否已配置（不显示明文）
    python cli.py clear        # 从 keyring 删除 key
    python cli.py run "任务描述" --workspace ./project --mock
    python cli.py run --task "任务描述" --workspace ./project --mock
"""

import argparse
import getpass
import json
import os
import sys

from src.agent import run
from src.llm_client import MockLLM, RealLLM
from src.parser import parse_llm_output
from src.validation import validate_action
from src.guardrail import assess_risk
import src.tools as tools

# Pre-set demo sequence for --mock mode: simulates a complete agent run
_MOCK_DEMO_RESPONSES = [
    json.dumps({"action": "list_files", "path": "."}),
    json.dumps({"action": "read_file", "path": "README.md"}),
    json.dumps({"action": "write_file", "path": "demo_output.txt",
                "content": "CodeGuard demo completed successfully.\n"}),
    json.dumps({"action": "finish", "summary": "Demo task completed"}),
]


def _check_api_key() -> bool:
    """Check whether an API Key is available via env var or keyring.

    Returns True if a key is found, False otherwise.
    Prints a friendly guide when no key is configured.
    """
    # 1) environment variable takes priority
    env_key = os.getenv("OPENAI_API_KEY", "")
    if env_key:
        print("[OK] Using API Key from environment variable")
        return True

    # 2) fall back to system keyring
    from src.keyring_manager import KeyringManager
    km = KeyringManager()
    if km.is_configured():
        return True

    # 3) nothing configured — print friendly guide
    print()
    print("[!] No API Key detected.")
    print("    First time? Run: python cli.py setup")
    print("    This securely stores your key in the system credential manager.")
    print("[X] Task cancelled.")
    return False


def cmd_setup(_args):
    from src.keyring_manager import KeyringManager
    km = KeyringManager()

    # warn if a key is already stored
    if km.is_configured():
        print("[!] An API Key already exists in the system credential manager.")
        confirm = input("    Overwrite? (y/n): ").strip().lower()
        if confirm != "y":
            print("[X] Cancelled, existing key unchanged.")
            return

    print("Enter your OpenAI API Key (input will be hidden):")
    api_key = getpass.getpass("API Key: ").strip()
    if not api_key:
        print("Error: API Key cannot be empty.")
        sys.exit(1)
    km.set_key(api_key)
    print("[OK] API Key saved to system credential manager.")


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
    if not args.task:
        print("Error: Task description is required.")
        sys.exit(1)
    if args.mock:
        print("[*] Running in mock mode (pre-set demo sequence, no API key needed)")
        llm = MockLLM(_MOCK_DEMO_RESPONSES)
    else:
        if not _check_api_key():
            sys.exit(1)
        llm = RealLLM()

    result = run(
        args.task,
        args.workspace,
        llm_client=llm,
        parse_fn=parse_llm_output,
        validate_fn=validate_action,
        assess_risk_fn=assess_risk,
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
    parser_run.add_argument("task", nargs="?", default=argparse.SUPPRESS, help="Task description for the agent")
    parser_run.add_argument("--task", dest="task", default=None, help="Task description for the agent (named form)")
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