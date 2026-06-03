#!/usr/bin/env python3
"""
patch_constants.py — 修补 console/src/layouts/constants.ts

将外部文档 URL (qwenpaw.agentscope.io) 替换为本地插件路由 (/api/erp/docs)
将 GitHub/PyPI URL 替换为空字符串或本地路径

此脚本在 replace_brand.py 之后运行，专门处理 constants.ts 中需要语义感知的替换
（不能简单做字符串替换，因为 URL 的路径部分需要调整）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def patch_constants(filepath: Path, docs_base_url: str = "/api/erp/docs", dry_run: bool = False) -> int:
    """修补 constants.ts 文件，返回替换次数。"""
    if not filepath.exists():
        print(f"  WARN: file not found: {filepath}")
        return 0

    content = filepath.read_text(encoding="utf-8")
    original = content
    count = 0

    # ── 1. 替换文档 URL ──
    # getDocsUrl: qwenpaw.agentscope.io/docs/intro → /api/erp/docs
    old_docs = r'https://qwenpaw\.agentscope\.io/docs/intro\?lang=\$\{getWebsiteLang\(lang\)\}'
    new_docs = f'{docs_base_url}?lang=${{getWebsiteLang(lang)}}'
    content, n = re.subn(old_docs, new_docs, content)
    count += n

    # getFaqUrl: qwenpaw.agentscope.io/docs/faq → /api/erp/docs/faq
    old_faq = r'https://qwenpaw\.agentscope\.io/docs/faq\?lang=\$\{getWebsiteLang\(lang\)\}'
    new_faq = f'{docs_base_url}/faq?lang=${{getWebsiteLang(lang)}}'
    content, n = re.subn(old_faq, new_faq, content)
    count += n

    # getReleaseNotesUrl: qwenpaw.agentscope.io/release-notes → /api/erp/docs/release-notes
    old_release = r'https://qwenpaw\.agentscope\.io/release-notes\?lang=\$\{getWebsiteLang\(lang\)\}'
    new_release = f'{docs_base_url}/release-notes?lang=${{getWebsiteLang(lang)}}'
    content, n = re.subn(old_release, new_release, content)
    count += n

    # getFeatureDemosUrl: qwenpaw.agentscope.io/docs/functiondemo → /api/erp/docs/functiondemo
    old_demo = r'https://qwenpaw\.agentscope\.io/docs/functiondemo\?lang=\$\{getWebsiteLang\(\s*lang\s*\)\}'
    new_demo = f'{docs_base_url}/functiondemo?lang=${{getWebsiteLang(lang)}}'
    content, n = re.subn(old_demo, new_demo, content)
    count += n

    # ── 2. 替换 PyPI URL ──
    content, n = re.subn(
        r'https://pypi\.org/pypi/qwenpaw/json',
        '',
        content
    )
    count += n

    # ── 3. 替换 GitHub URL ──
    content, n = re.subn(
        r'https://github\.com/agentscope-ai/QwenPaw',
        '',
        content
    )
    count += n

    # ── 4. 替换 UPDATE_MD 中的品牌名和 Docker 命令 ──
    # UPDATE_MD 中包含硬编码的 QwenPaw 品牌名和 Docker 镜像引用
    # 这些更新提示在白标环境中无意义，直接清空
    # 保留结构但内容改为"请联系管理员更新"
    content, n = re.subn(
        r'### QwenPaw.*?After upgrading, restart the service with `qwenpaw app`\.',
        '### Update\n\nPlease contact your system administrator for updates.',
        content,
        flags=re.DOTALL
    )
    count += n

    # 中文版更新说明
    content, n = re.subn(
        r'### QwenPaw.*?重启 qwenpaw app，',
        '### 更新\n\n请联系系统管理员进行版本更新。',
        content,
        flags=re.DOTALL
    )
    count += n

    # 俄文版更新说明（类似模式）
    content, n = re.subn(
        r'### .*?QwenPaw.*?`qwenpaw app`\.',
        '### Обновление\n\nПожалуйста, свяжитесь с системным администратором для обновлений.',
        content,
        flags=re.DOTALL
    )
    count += n

    if content != original and not dry_run:
        filepath.write_text(content, encoding="utf-8")
        print(f"  OK {filepath}: {count} replacements")
    elif content != original and dry_run:
        print(f"  [DRY] {filepath}: {count} replacements estimated")

    return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="修补 constants.ts")
    parser.add_argument("--src", default="/app", help="QwenPaw 源码根目录")
    parser.add_argument("--docs-url", default="/api/erp/docs", help="文档 URL 前缀")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    filepath = Path(args.src) / "console" / "src" / "layouts" / "constants.ts"
    n = patch_constants(filepath, args.docs_url, args.dry_run)
    print(f"\n{'ESTIMATED' if args.dry_run else 'DONE'}: {n} replacements")


if __name__ == "__main__":
    main()
