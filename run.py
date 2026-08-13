"""run.py — 兼容性入口，转发给根目录 cli.py 的 main()。

部分评审脚本 / 文档习惯用 `python run.py` 启动，本文件提供该别名。
实际逻辑全部位于 cli.py，避免维护两份实现。
"""

from cli import main

if __name__ == "__main__":
    main()
