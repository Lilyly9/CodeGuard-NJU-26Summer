# CodeGuard — AI Coding Agent with Governance Guardrails

> NJU 26 暑期智能软件工程师训练营课程作业

CodeGuard 是一个带有**确定性代码护栏**的 AI 编程助手。它在 LLM 与操作系统之间建立硬性安全层，通过 Python 代码而非提示词实现风险分级、拦截和人工审批。

## 核心特性

- **硬护栏而非软提示**：风险识别、分级、拦截均由代码实现，不依赖 LLM 自觉
- **可测试的安全机制**：所有治理逻辑可通过 MockLLM 在无网络环境下验证
- **人机协同（HITL）**：高风险操作必须经人工审批，防止自动化失控
- **反馈闭环**：测试结果、命令退出码等客观信号回灌给 LLM，驱动自我修正

## 安装与依赖

```bash
# 克隆仓库
git clone <repo-url>
cd CodeGuard-NJU-26Summer

# 安装依赖
pip install -r requirements.txt
```

## API Key 安全配置

### 方式一：本地推荐（系统钥匙串）

```bash
python -m src.keyring_manager --set
```

密钥将安全存储在系统凭据管理器（Windows Credential Manager / macOS Keychain / Linux Secret Service），不写入任何文件。

### 方式二：Docker / CI 环境

```bash
export OPENAI_API_KEY=sk-xxx
```

当环境变量 `OPENAI_API_KEY` 存在时，优先使用环境变量，否则回退到系统 keyring。若两者均为空，程序将抛出 `ValueError` 并终止。

## 运行方式

### CLI

```bash
python cli.py run --workspace ./my_project --task "你的任务"
```

### WebUI

```bash
python webui/app.py
```

打开浏览器访问 http://localhost:5000

### Docker

```bash
# 构建镜像
docker build -t codeguard .

# 运行 WebUI
docker run -it --rm -p 5000:5000 -e OPENAI_API_KEY=sk-xxx -v ./my_project:/app/workspace codeguard

# 若想运行 CLI，覆盖 CMD
docker run -it --rm -v ./my_project:/app/workspace -e OPENAI_API_KEY=sk-xxx codeguard python cli.py --workspace /app/workspace --task "你的任务"
```

## 三机制演示

三个确定性剧本，使用 MockLLM 驱动，不联网：

```bash
python demo.py
```

| 剧本 | 说明 | 预期 |
|------|------|------|
| Demo 1 | 拦截危险命令 `rm -rf /` | BLOCKED |
| Demo 2 | 高风险操作被用户拒绝 | REJECTED |
| Demo 3 | 修改代码 → 运行测试 → 通过 | EXECUTED |

## 测试

```bash
# 运行所有单元测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_agent.py -v
pytest tests/test_guardrail.py -v
pytest tests/test_validation.py -v
```

## 安全设计

### API Key 安全存储

- 使用 `keyring` 库，密钥存入系统凭据管理器（Windows Credential Manager / macOS Keychain / Linux Secret Service）
- 不写入 `.env`、配置文件或日志
- 审计日志自动过滤 `api_key`、`token`、`secret` 等敏感字段

### 路径沙箱

- 使用 `os.path.commonpath()` 硬检查，确保所有文件操作在 workspace 内
- 黑名单优先：`.env`、`*.pem`、`*.key`、`.git` 直接拒绝

### 命令沙箱

- 仅白名单命令：`pytest`、`python`、`ruff`、`git diff`、`git status`
- 禁止 Shell 控制符：`;`、`&&`、`||`、`|`
- `subprocess.run` 使用 `shell=False`，环境变量仅保留 `PATH`

### 四级风险分级

| 级别 | 动作 | 处理 |
|------|------|------|
| LOW | `list_files`, `read_file`, `git status` | 自动执行 |
| MEDIUM | `write_file`, `edit_file`, `run_pytest` | 自动执行，记录 diff |
| HIGH | `rm`, `git commit` | 暂停，请求人工审批 |
| FORBIDDEN | `rm -rf /`, `..` 路径穿越, `.env` 读取 | 直接拦截，不可绕过 |

## 项目结构

- **`src/`** — 核心逻辑：Agent 主循环、护栏、解析器、验证器、工具实现等
- **`webui/`** — 可视化界面：基于 Flask 的 Web 交互入口
- **`tests/`** — 单元测试：覆盖所有模块，支持 MockLLM 离线运行

```
codeguard/
├── cli.py                  # 命令行入口
├── demo.py                 # 三机制演示脚本
├── Dockerfile              # Docker 构建文件
├── .dockerignore           # Docker 忽略规则
├── pyproject.toml          # 项目元数据
├── config.toml             # 默认配置
├── conftest.py             # pytest 全局 fixture
├── src/
│   ├── agent.py            # 主循环
│   ├── approval.py         # 人工审批
│   ├── audit_log.py        # 审计日志
│   ├── config.py           # 配置加载
│   ├── executor.py         # 工具分发
│   ├── feedback.py         # 反馈构建
│   ├── guardrail.py        # 风险分级
│   ├── keyring_manager.py  # 凭据管理
│   ├── llm_client.py       # LLM 抽象层
│   ├── memory.py           # 会话记忆
│   ├── models.py           # 数据模型
│   ├── parser.py           # LLM 输出解析
│   ├── tools.py            # 七大工具实现
│   └── validation.py       # 预执行验证
├── webui/
│   └── app.py              # Flask Web 界面
└── tests/
    ├── test_agent.py
    ├── test_approval.py
    ├── test_audit_log.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_demo.py
    ├── test_executor.py
    ├── test_feedback.py
    ├── test_guardrail.py
    ├── test_keyring_manager.py
    ├── test_llm_client.py
    ├── test_memory.py
    ├── test_models.py
    ├── test_parser.py
    ├── test_tools.py
    └── test_validation.py
```

## 配置说明

编辑 `config.toml` 自定义行为：

```toml
[agent]
workspace = "."
max_steps = 10
command_timeout = 30
max_file_size = 100000
auto_finish_on_test_pass = true
allowed_commands = ["pytest", "python", "ruff", "git diff", "git status"]
protected_files = [".env", "*.pem", "*.key", ".git"]
```

## 已知限制

- **TOCTOU 符号链接攻击未完全防护**：路径检查使用 `os.path.realpath()` + `os.path.commonpath()`，但符号链接在检查与执行之间可能被替换（Time-of-check to time-of-use）。已在 SPEC §16 记录为 P2 计划项，第一版仅记录风险。
- **keyring 在无图形界面的 Linux 服务器上可能不可用**：`keyring` 依赖系统凭据管理器（Windows Credential Manager / macOS Keychain / Linux Secret Service）。在 headless Linux 环境（如某些 CI/容器）中，Secret Service 后端可能需要 `dbus` 支持；此时请改用环境变量 `OPENAI_API_KEY` 作为后备。
- **WebUI 仅本地部署，未提供公网 URL**：`webui/app.py` 默认运行在 `localhost:5000`，需自行部署到 Render/Vercel 等平台以获得公网访问。

## 许可证

课程作业，仅用于教学演示。