"""Tool 执行器 — 将解析后的动作分发到对应的工具函数。

execute_tool(action, params, workspace, config) 返回 ToolResult 字典。
"""


def execute_tool(action: str, params: dict, workspace: str, config, tools_module=None) -> dict:
    if tools_module is None:
        import src.tools as tools_module

    if action == "list_files":
        path = params.get("path", workspace)
        return tools_module.list_files(path, workspace)
    elif action == "read_file":
        return tools_module.read_file(params["path"], workspace)
    elif action == "write_file":
        return tools_module.write_file(params["path"], params["content"], workspace, config)
    elif action == "edit_file":
        return tools_module.edit_file(
            params["path"],
            int(params["start_line"]),
            int(params["end_line"]),
            params["new_content"],
            workspace,
        )
    elif action == "run_pytest":
        return tools_module.run_pytest(workspace)
    elif action == "run_command":
        return tools_module.run_command(params["command"], workspace)
    elif action == "finish":
        return {"success": True, "data": params.get("summary", ""), "error": None, "meta": {"finished": True}}
    else:
        return {"success": False, "data": None, "error": f"Unknown action: {action}", "meta": {}}