"""Disabled. Do not probe multiple models from Cursor."""
from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.exit(
        "已禁用：禁止从 Cursor 连打多个重排/生成模型。"
        "正式实验只使用 config.yaml / experiments/configs 里写死的那一个百炼模型，"
        "且须你明确下令后才跑。"
    )
