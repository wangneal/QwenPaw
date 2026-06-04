# -*- coding: utf-8 -*-
"""Hallucination-guard mixin for QwenPawAgent.

Provides ``_acting`` override that intercepts hallucination-driven
tool calls before execution: file-path validation, schema checking,
and correction-hint injection.

Placed before ``ToolGuardMixin`` in the MRO so it runs first:

    QwenPawAgent -> HallucinationGuardMixin -> CodingModeMixin
        -> ToolGuardMixin -> ReActAgent
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
from pathlib import Path
from typing import Any

from agentscope.message import Msg, ToolResultBlock

logger = logging.getLogger(__name__)


# ======================================================================
# P1.1 — 辅助函数
# ======================================================================


def _extract_file_refs_from_cmd(cmd: str) -> list[str]:
    """从 shell 命令中提取可能的文件路径引用。

    匹配模式：
    - 绝对路径:    /path/to/file, C:\\path\\to\\file
    - 相对路径:    ./path, ../path
    - 重定向目标:  > file.txt, >> file.txt
    - 等号赋值:    --file=path, -f /path

    返回去重后的路径列表，过滤掉长度 <= 3 的短匹配（避免匹配 `C:` 等）。
    """
    if not cmd:
        return []

    paths: list[str] = []

    # 绝对/相对路径（含引号保护和 Windows 盘符）
    for m in re.finditer(
        r"""(?:^|\s|["'])((?:/|\.\.?/|[A-Za-z]:\\)[^\s"'<>|&;]+)""",
        cmd,
    ):
        paths.append(m.group(1).strip("'\""))

    # 重定向目标 > file, >> file
    for m in re.finditer(r">+\s*([^\s;|&\"']+)", cmd):
        paths.append(m.group(1))

    # --flag=value 或 --flag:value
    for m in re.finditer(
        r"--?[\w-]+[=:](/[^\s\"']+|[A-Za-z]:\\[^\s\"']+)",
        cmd,
    ):
        paths.append(m.group(1))

    # 去重并过滤短匹配
    seen: set[str] = set()
    result: list[str] = []
    for p in paths:
        if len(p) > 3 and p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _validate_tool_input(tool_fn: Any, tool_input: dict[str, Any]) -> list[str]:
    """校验工具输入是否符合函数签名定义的 schema。

    使用 ``inspect.signature`` 自动推导函数签名，无需手动定义 schema。
    宽松类型转换策略：``int("5")`` 通过，``int("abc")`` 才失败。

    Returns:
        violations: 校验失败列表，空列表表示通过。
    """
    violations: list[str] = []
    try:
        sig = inspect.signature(tool_fn)
    except (ValueError, TypeError):
        # 无法获取签名（C 扩展函数等），跳过校验
        return violations

    for name, param in sig.parameters.items():
        if name in tool_input:
            expected_type = param.annotation
            if expected_type is not inspect.Parameter.empty:
                try:
                    # 宽松类型转换
                    expected_type(tool_input[name])  # type: ignore[operator]
                except (ValueError, TypeError):
                    violations.append(
                        f"参数 '{name}' 类型错误: "
                        f"期望 {getattr(expected_type, '__name__', str(expected_type))}, "
                        f"实际 {type(tool_input[name]).__name__}",
                    )
        elif param.default is inspect.Parameter.empty:
            # 必填参数缺失
            violations.append(f"缺少必填参数: '{name}'")

    return violations


# ======================================================================
# P1.2 — HallucinationGuardMixin 类
# ======================================================================


class HallucinationGuardMixin:
    """代码级幻觉防护 — 校验工具调用参数的真实性。

    在 ``ToolGuardMixin`` 之前拦截工具调用，执行以下校验：
    - L2: 文件路径存在性校验 + 目录鉴别
    - L2: Shell 命令中引用的文件存在性校验
    - L1: 函数参数 Schema 类型校验
    - 阻断时注入修正引导到 memory，构成反馈循环

    MRO 要求
    ~~~~~~~~
    MRO: QwenPawAgent → ``HallucinationGuardMixin`` → CodingModeMixin
         → ToolGuardMixin → ReActAgent.

    每个 ``_acting`` override **必须** 调用 ``super()._acting(...)`` 以保持链路完整。
    CodingModeMixin 不覆盖 ``_acting``，因此 ``super()`` 会正确跳到 ToolGuardMixin。
    """

    # 需要文件路径存在性校验的工具
    PATH_VALIDATION_TOOLS: frozenset[str] = frozenset({
        "read_file",
        "edit_file",
        "write_file",
        "grep_search",
        "view_image",
        "view_video",
    })

    # 查询类工具 — 返回空时可能触发空结果声明（通过 post_acting hook）
    QUERY_TOOLS: frozenset[str] = frozenset({
        "grep_search",
        "glob_search",
        "read_file",
    })

    # 需要绝对路径存在（父目录不行）的工具
    STRICT_PATH_TOOLS: frozenset[str] = frozenset({
        "read_file",
        "edit_file",
        "view_image",
        "view_video",
    })

    # 允许仅父目录存在的工具（新建文件场景）
    PARENT_DIR_OK_TOOLS: frozenset[str] = frozenset({
        "write_file",
    })

    # ------------------------------------------------------------------
    # _acting override
    # ------------------------------------------------------------------

    async def _acting(self, tool_call: dict[str, Any]) -> dict | None:  # type: ignore[override]
        """拦截幻觉驱动的工具调用。

        执行顺序（在 ToolGuardMixin 之前）：
        1. L2 — 文件路径存在性校验 + 目录鉴别
        2. L2 — Shell 命令引用文件校验
        3. L1 — Schema 类型校验
        4. → 调用 ``super()._acting()``（传递到 ToolGuardMixin）
        """
        tool_name = str(tool_call.get("name", ""))
        tool_input = tool_call.get("input", {})

        # --------------------------------------------------------------
        # 1. L2 — 文件路径存在性校验 + 目录鉴别
        # --------------------------------------------------------------
        if tool_name in self.PATH_VALIDATION_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("path")
            if path:
                error = self._check_path(tool_name, str(path))
                if error:
                    hint = self._build_correction_hint(tool_name, tool_input)
                    await self.memory.add(Msg(name="system", role="system", content=f"[修正引导] {hint}"))
                    await self._block(tool_call, error)
                    return None

        # --------------------------------------------------------------
        # 2. L2 — Shell 命令引用文件校验
        # --------------------------------------------------------------
        if tool_name == "execute_shell_command":
            cmd = tool_input.get("command", "")
            for ref_path in _extract_file_refs_from_cmd(str(cmd)):
                if not Path(ref_path).exists():
                    await self._block(
                        tool_call,
                        f"命令引用的文件不存在: {ref_path}",
                    )
                    return None

        # --------------------------------------------------------------
        # 3. L1 — Schema 类型校验
        # --------------------------------------------------------------
        violations = await self._validate_schema(tool_name, tool_input)
        if violations:
            hint = self._build_correction_hint(tool_name, tool_input)
            await self.memory.add(Msg(name="system", role="system", content=f"[修正引导] {hint}"))
            await self._block(tool_call, "参数校验失败: " + "; ".join(violations))
            return None

        # --------------------------------------------------------------
        # 4. 传递到下个 Mixin
        # --------------------------------------------------------------
        return await super()._acting(tool_call)  # type: ignore[misc]

    # ------------------------------------------------------------------
    # 内部分支方法
    # ------------------------------------------------------------------

    def _check_path(self, tool_name: str, path: str) -> str | None:
        """检查路径有效性。返回错误消息或 None（校验通过）。"""
        p = Path(path)

        if not p.exists():
            # write_file 允许父目录存在（新建文件场景）
            if tool_name in self.PARENT_DIR_OK_TOOLS and p.parent.exists():
                return None
            return f"路径不存在: {path}"

        if tool_name in self.STRICT_PATH_TOOLS and p.is_dir():
            return f"路径是目录而非文件: {path}"

        return None

    async def _validate_schema(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> list[str]:
        """对工具输入运行 Schema 校验。

        MCP 工具是动态注册的，toolkit 中可能没有对应函数。
        如果无法获取函数签名，跳过 Schema 校验（仅做路径校验）。
        """
        tool_fn = await self._get_tool_fn(tool_name)
        if tool_fn is None:
            return []  # MCP 工具 — 跳过 Schema 校验
        return _validate_tool_input(tool_fn, tool_input)

    async def _get_tool_fn(self, tool_name: str):
        """获取工具函数对象。

        适配 agentscope Toolkit 的多种可能 API 命名：
        ``tool_functions_map`` → ``_tool_functions`` → ``tools``.
        """
        toolkit = getattr(self, "toolkit", None)
        if toolkit is None:
            return None
        # 轮询可能存在的属性名（兼容不同 agentscope 版本）
        for attr in ("tool_functions_map", "_tool_functions", "tools"):
            func_map = getattr(toolkit, attr, None)
            if isinstance(func_map, dict) and tool_name in func_map:
                return func_map[tool_name]
        return None

    async def _block(self, tool_call: dict[str, Any], reason: str) -> None:
        """阻断工具调用 — 将阻断消息写入 memory 后立即返回。

        注意：本方法只负责写入阻断消息，不返回值。
        调用方应在 ``_block`` 后自行 ``return None``。
        这与 ``ToolGuardMixin`` 中 ``_acting_auto_denied`` 的模式一致。
        """
        tool_name = str(tool_call.get("name", ""))
        tool_id = str(tool_call.get("id", ""))
        block_msg = Msg(
            name="system",
            role="system",
            content=[
                ToolResultBlock(
                    type="tool_result",
                    id=tool_id,
                    name=tool_name,
                    output=[{
                        "type": "text",
                        "text": f"[幻觉防护][{tool_name}]: {reason}\n"
                        f"请先通过查询工具获取真实值，不要猜测或编造。",
                    }],
                ),
            ],
        )
        await self.memory.add(block_msg)

    def _build_correction_hint(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> str:
        """构建修正引导 — Harness 原则：不只说错了，还教正确做法。

        修正引导会被注入到 ``memory``，LLM 下一轮推理时能看到并自我修正。
        """
        hints: dict[str, str] = {
            "read_file": "请先用 glob_search 搜索正确的文件路径。",
            "edit_file": "请先用 read_file 确认文件存在后再编辑。",
            "write_file": "如需新建文件，请确认父目录路径正确。",
            "grep_search": "请先用 glob_search 确认目录结构后再搜索。",
            "execute_shell_command": (
                "命令中引用了不存在的文件。"
                "请先用 glob_search / read_file 确认文件存在。"
            ),
        }
        hint = hints.get(tool_name)
        if hint:
            return hint

        # 通用修正引导
        values = ", ".join(str(k) for k in list(tool_input.keys())[:3])
        return f"参数校验失败。请先通过查询工具获取真实值。传入的参数: {values}"
