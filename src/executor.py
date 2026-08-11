"""执行器 — 根据 Action 分发到 tools.py 对应函数，返回 ToolResult。"""

from src.models import Action, ToolResult


def execute(action: Action, workspace: str, tools_module=None) -> ToolResult:
    if tools_module is None:
        import src.tools as tools_module

    action_type = action.type
    params = action.params

    if action_type == "list_files":
        path = params.get("path", workspace)
        result = tools_module.list_files(path, workspace)
    elif action_type == "read_file":
        result = tools_module.read_file(params.get("path", ""), workspace)
    elif action_type == "write_file":
        result = tools_module.write_file(
            params.get("path", ""), params.get("content", ""), workspace
        )
    elif action_type == "run_tests":
        result = tools_module.run_tests(workspace)
    elif action_type == "run_command":
        result = tools_module.run_command(params.get("command", ""), workspace)
    else:
        return ToolResult(success=False, error=f"Unknown action: {action_type}")

    return ToolResult(
        success=result.get("success", False),
        data=result.get("data"),
        error=result.get("error"),
        meta=result.get("meta", {}),
    )