#!/usr/bin/env python3
"""
brand_overlay.py — QwenPaw 白标品牌替换脚本

在 Docker 构建阶段运行，将 QwenPaw 品牌替换为自有品牌。

用法:
    python brand_overlay.py --src /app --brand "星智" --brand-en "StarMind"

环境变量（也可通过命令行参数覆盖）:
    QWENPAW_SRC      — QwenPaw 源码根目录（默认 /app）
    BRAND_NAME_ZH    — 中文品牌名（默认 "星智"）
    BRAND_NAME_EN    — 英文品牌名（默认 "StarMind"）
    DOCS_BASE_URL    — 使用文档基础 URL（默认 "/api/erp/docs"）
"""

from __future__ import annotations

import json
import os
import re
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field


# ─── 配置 ──────────────────────────────────────────────────────────────

@dataclass
class BrandConfig:
    src: Path                  # QwenPaw 源码根目录
    brand_zh: str              # 中文品牌名
    brand_en: str              # 英文品牌名
    docs_base_url: str         # 内置文档 URL 前缀

    # 品牌名替换映射（源 → 目标），初始化时自动生成
    name_replacements: dict[str, str] = field(init=False, default_factory=dict)
    # URL 替换映射
    url_replacements: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self.src = Path(self.src)
        # 品牌名替换：大小写变体都要覆盖
        self.name_replacements = {
            "QwenPaw":  self.brand_en,
            "qwenpaw":  self.brand_en.lower().replace(" ", ""),
            "QWENPAW":  self.brand_en.upper().replace(" ", ""),
            "Qwen Paw": self.brand_en,
            "qwen-paw": self.brand_en.lower().replace(" ", "-"),
        }
        # URL 替换
        self.url_replacements = {
            "https://qwenpaw.agentscope.io": self.docs_base_url,
            "https://qwenpaw.agentscope.io/": self.docs_base_url + "/",
            "http://qwenpaw.agentscope.io": self.docs_base_url,
            "qwenpaw.agentscope.io": self.docs_base_url.lstrip("/"),
            # GitHub 链接 → 空字符串（移除）
            "https://github.com/modelscope/qwenpaw": "",
            "https://github.com/modelscope/QwenPaw": "",
        }


# ─── 可删除的目录/文件 ────────────────────────────────────────────────

REMOVABLE_PATHS = [
    # 目录
    "website",
    "tests",
    "e2e",
    "plugins/bundle/qwenpaw-pet",
    "plugins/bundle/cloudpaw",
    # 根目录 GitHub 文件
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING_zh.md",
    "README.md",
    "README_zh.md",
    "README_ja.md",
    "README_ru.md",
    "README_pt-BR.md",
]


# ─── 需要品牌替换的目标文件（白名单） ────────────────────────────────

# Console 前端 locales
LOCALE_FILES = [
    "console/src/locales/en.json",
    "console/src/locales/zh.json",
    "console/src/locales/ja.json",
    "console/src/locales/ru.json",
    "console/src/locales/pt-BR.json",
    "console/src/locales/id.json",
]

# Console 前端源码
CONSOLE_SRC_FILES = [
    "console/src/layouts/Header.tsx",
    "console/tauri.html",
]

# Python 后端
BACKEND_FILES = [
    "src/qwenpaw/utils/startup_display.py",
    "src/qwenpaw/utils/console_static.py",
    "src/qwenpaw/cli/update_cmd.py",
    "src/qwenpaw/cli/doctor_cmd.py",
    "src/qwenpaw/agents/skill_system/hub.py",
    "src/qwenpaw/constant.py",
]

# 需要替换的 Logo/图片文件（由外部文件覆盖，脚本不做文本替换）
LOGO_FILES = [
    "console/public/qwenpaw.png",
    "console/public/qwenpawBack.png",
    "console/public/logo-dark.svg",
    "console/public/logo-light.svg",
    "scripts/pack/assets/icon.ico",
    "scripts/pack/assets/icon.svg",
]


# ─── 核心替换逻辑 ──────────────────────────────────────────────────────

def remove_unneeded(src: Path, dry_run: bool = False) -> list[str]:
    """删除不需要的目录和文件，返回实际删除的路径列表。"""
    removed = []
    for rel in REMOVABLE_PATHS:
        target = src / rel
        if target.exists():
            removed.append(rel)
            if not dry_run:
                if target.is_dir():
                    import shutil
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
    return removed


def replace_in_file(filepath: Path, replacements: dict[str, str], dry_run: bool = False) -> int:
    """在单个文件中执行字符串替换，返回替换次数。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return 0

    count = 0
    for old, new in replacements.items():
        occurrences = content.count(old)
        if occurrences > 0:
            content = content.replace(old, new)
            count += occurrences

    if count > 0 and not dry_run:
        filepath.write_text(content, encoding="utf-8")

    return count


def replace_in_json(filepath: Path, replacements: dict[str, str], dry_run: bool = False) -> int:
    """在 JSON 文件中执行替换，保持 JSON 格式。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return 0

    count = 0
    for old, new in replacements.items():
        occurrences = content.count(old)
        if occurrences > 0:
            content = content.replace(old, new)
            count += occurrences

    if count > 0 and not dry_run:
        # 验证 JSON 仍然合法
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            print(f"  WARN: JSON validation failed {filepath}: {e}")
            return 0
        filepath.write_text(content, encoding="utf-8")

    return count


def process_locale_files(src: Path, cfg: BrandConfig, dry_run: bool = False) -> dict[str, int]:
    """处理所有 locale JSON 文件。"""
    results = {}
    all_replacements = {**cfg.name_replacements, **cfg.url_replacements}

    for rel in LOCALE_FILES:
        filepath = src / rel
        if not filepath.exists():
            continue
        n = replace_in_json(filepath, all_replacements, dry_run)
        if n > 0:
            results[rel] = n
    return results


def process_console_src(src: Path, cfg: BrandConfig, dry_run: bool = False) -> dict[str, int]:
    """处理 Console 前端 TS/TSX/HTML 文件。"""
    results = {}
    all_replacements = {**cfg.name_replacements, **cfg.url_replacements}

    for rel in CONSOLE_SRC_FILES:
        filepath = src / rel
        if not filepath.exists():
            continue
        n = replace_in_file(filepath, all_replacements, dry_run)
        if n > 0:
            results[rel] = n
    return results


def process_backend(src: Path, cfg: BrandConfig, dry_run: bool = False) -> dict[str, int]:
    """处理 Python 后端文件。"""
    results = {}
    # 后端只替换品牌名和 URL，不改环境变量前缀（constant.py 中的 QWENPAW_ 前缀保留）
    # 但 constant.py 中的用户可见字符串需要替换
    all_replacements = {**cfg.name_replacements, **cfg.url_replacements}

    for rel in BACKEND_FILES:
        filepath = src / rel
        if not filepath.exists():
            continue
        # constant.py 特殊处理：只替换用户可见字符串，不替换环境变量前缀
        if rel == "src/qwenpaw/constant.py":
            n = replace_in_file(filepath, cfg.name_replacements, dry_run)
        else:
            n = replace_in_file(filepath, all_replacements, dry_run)
        if n > 0:
            results[rel] = n
    return results


def replace_logos(src: Path, logo_dir: Path, dry_run: bool = False) -> list[str]:
    """从 logo_dir 复制替换 Logo 文件。"""
    replaced = []
    for rel in LOGO_FILES:
        target = src / rel
        # 推导源文件名：取最后的文件名
        source_name = Path(rel).name
        source = logo_dir / source_name

        if source.exists() and target.exists():
            replaced.append(rel)
            if not dry_run:
                import shutil
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    return replaced


# ─── 主流程 ────────────────────────────────────────────────────────────

def run(cfg: BrandConfig, dry_run: bool = False):
    """执行白标替换。"""
    mode = "[DRY RUN]" if dry_run else "[EXECUTING]"
    print(f"\n{mode} -- QwenPaw White-Label Brand Replacement")
    print(f"  Source: {cfg.src}")
    print(f"  Brand ZH: {cfg.brand_zh}")
    print(f"  Brand EN: {cfg.brand_en}")
    print(f"  Docs URL: {cfg.docs_base_url}")
    print()

    if not cfg.src.exists():
        print(f"[ERROR] Source dir not found: {cfg.src}")
        sys.exit(1)

    # ── 1. 删除不需要的目录/文件 ──
    print("[1] Remove unneeded directories/files")
    removed = remove_unneeded(cfg.src, dry_run)
    for r in removed:
        print(f"  DEL {r}")
    if not removed:
        print("  (nothing to remove)")
    print()

    # ── 2. Locale JSON brand replacement ──
    print("[2] Locale file brand replacement")
    locale_results = process_locale_files(cfg.src, cfg, dry_run)
    for rel, n in locale_results.items():
        print(f"  OK {rel}: {n} replacements")
    if not locale_results:
        print("  (no replacements)")
    print()

    # ── 3. Console source replacement ──
    print("[3] Console source code replacement")
    console_results = process_console_src(cfg.src, cfg, dry_run)
    for rel, n in console_results.items():
        print(f"  OK {rel}: {n} replacements")
    if not console_results:
        print("  (no replacements)")
    print()

    # ── 4. Python backend replacement ──
    print("[4] Python backend brand replacement")
    backend_results = process_backend(cfg.src, cfg, dry_run)
    for rel, n in backend_results.items():
        print(f"  OK {rel}: {n} replacements")
    if not backend_results:
        print("  (no replacements)")
    print()

    # ── 5. Logo file replacement ──
    logo_dir = Path(__file__).parent / "logos"
    print("[5] Logo file replacement")
    if logo_dir.exists():
        logo_results = replace_logos(cfg.src, logo_dir, dry_run)
        for r in logo_results:
            print(f"  OK {r}")
        if not logo_results:
            print("  (logo dir empty or target files missing)")
    else:
        print(f"  SKIP: logo dir not found: {logo_dir}")
    print()

    # ── Summary ──
    total = sum(locale_results.values()) + sum(console_results.values()) + sum(backend_results.values())
    prefix = "ESTIMATED" if dry_run else "DONE"
    print(f"{prefix}: {total} brand references replaced, {len(removed)} dirs/files removed")


def main():
    parser = argparse.ArgumentParser(description="QwenPaw 白标品牌替换脚本")
    parser.add_argument("--src", default=os.getenv("QWENPAW_SRC", "/app"),
                        help="QwenPaw 源码根目录")
    parser.add_argument("--brand", default=os.getenv("BRAND_NAME_ZH", "金蝶ERP助手"),
                        help="中文品牌名")
    parser.add_argument("--brand-en", default=os.getenv("BRAND_NAME_EN", "KD ERP Assistant"),
                        help="英文品牌名")
    parser.add_argument("--docs-url", default=os.getenv("DOCS_BASE_URL", "/api/erp/docs"),
                        help="内置使用文档 URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅预览替换，不实际修改文件")
    args = parser.parse_args()

    cfg = BrandConfig(
        src=Path(args.src),
        brand_zh=args.brand,
        brand_en=args.brand_en,
        docs_base_url=args.docs_url,
    )
    run(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
