"""用户设置（上次打开的卡、导出格式、界面语言等），存在用户目录下的一个 JSON 文件里。"""

import json
import os

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".pcsx2_memcard_manager.json")


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
