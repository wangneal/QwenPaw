# -*- coding: utf-8 -*-
"""Anti-hallucination tool mixin — L0 code-level enforcement base class.

All tool functions can inherit from this mixin to automatically get:
- **Parameter whitelist validation**: ``PARAM_WHITELISTS``
- **Two-step execution guard**: ``enforce_two_step()``
- **Empty result declaration**: ``declare_if_empty()``
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any


class AntiHallucinationToolMixin:
    """工具防幻觉基类 — 所有工具可继承获得 L0 防护能力。

    子类通过类变量声明需要哪些防护，基类自动强制执行。

    用法::

        class MyTool(AntiHallucinationToolMixin):
            PARAM_WHITELISTS = {
                "form_id": {"SAL_SaleOrder", "PUR_PurchaseOrder"},
            }
            REQUIRES_PREVIEW = True
            DECLARE_EMPTY_RESULT = True

    注意：该 Mixin 适用于类形式的工具（如插件工具）。
    模块级函数工具需手动调用 ``enforce_two_step()`` / ``declare_if_empty()``。
    """

    # 参数白名单: {参数名: {合法值集合}}
    PARAM_WHITELISTS: dict[str, set[str]] = {}

    # 是否需要双步调用 (execute=False 预览 -> execute=True 执行)
    REQUIRES_PREVIEW: bool = False

    # 是否需要空结果声明
    DECLARE_EMPTY_RESULT: bool = False

    def __init__(self) -> None:
        self._preview_lock = asyncio.Lock()
        self._previewed_keys: set[str] = set()

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    async def validate_param_against_whitelist(
        self,
        param_name: str,
        value: str,
    ) -> str | None:
        """校验参数值是否在白名单中。

        Args:
            param_name: 参数名。
            value: 参数值。

        Returns:
            错误消息或 None（校验通过）。
        """
        whitelist = self.PARAM_WHITELISTS.get(param_name)
        if whitelist and value not in whitelist:
            return (
                f"参数 '{param_name}' 的值 '{value}' 不在合法集合中。"
                f"请先通过查询工具获取有效值。"
            )
        return None

    async def enforce_two_step(self, execute: bool, params: dict) -> dict | None:
        """强制双步调用：未预览则拒绝执行。

        Args:
            execute: 是否执行。False 生成预览，True 执行前检查指纹。
            params: 操作参数（用于生成指纹）。

        Returns:
            None: 校验通过（允许执行）。
            dict: 校验失败（返回预览或错误消息）。
        """
        pkey = self._compute_preview_key(params)
        if not execute:
            async with self._preview_lock:
                self._previewed_keys.add(pkey)
            return {"preview": params, "status": "pending"}

        async with self._preview_lock:
            if pkey not in self._previewed_keys:
                return {
                    "error": "请先执行预览 (execute=False) 确认操作，"
                    "然后再执行 (execute=True)。",
                }
        return None

    async def declare_if_empty(
        self,
        results: list | dict | None,
        tool_name: str,
    ) -> str | None:
        """查询结果为空时，返回防幻觉声明。

        Args:
            results: 工具查询结果。
            tool_name: 工具名称（用于声明文本）。

        Returns:
            防幻觉声明文本，或 None（结果非空）。
        """
        if not results:
            return (
                f"【{tool_name} 返回空结果】\n"
                f"请核实查询条件，不要编造替代答案或虚构数据。"
            )
        return None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _compute_preview_key(self, params: dict) -> str:
        """生成预览操作的唯一标识（MD5 指纹）。"""
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()[:16]
