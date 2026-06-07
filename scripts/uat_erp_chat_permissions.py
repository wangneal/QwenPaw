#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金蝶 ERP Agent 黑盒 UAT：聊天接口与权限接口。

该脚本面向本地 Docker/开发环境，所有 ERP 写入类聊天用例只验证预览与拦截，
不发送 execute=True，避免误写真实账套。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


DEFAULT_AGENTS = [
    "default",
    "erp-finance",
    "erp-sales",
    "erp-purchase",
    "erp-inventory",
    "erp-executive",
]

EXPECTED_ERP_TOOLS = [
    "kingdee_list_user_orgs",
    "kingdee_query_bill",
    "kingdee_view_bill",
    "kingdee_get_report",
    "kingdee_get_kds_report",
    "kingdee_save_bill",
    "kingdee_delete_bill",
    "kingdee_submit_bill",
    "kingdee_audit_bill",
    "kingdee_unaudit_bill",
    "kingdee_push_bill",
    "kingdee_execute_operation",
    "kingdee_workflow_audit",
    "kingdee_switch_org",
    "kingdee_query_metadata",
    "kingdee_search_form",
    "kingdee_product_qa",
    "kingdee_list_digest_templates",
    "kingdee_allocate_base_data",
    "kingdee_cancel_allocate_base_data",
    "kingdee_group_save_base_data",
    "kingdee_query_group_info",
    "kingdee_query_group_by_business_key",
    "kingdee_group_delete_base_data",
    "kingdee_create_group_under_parent",
    "kingdee_delete_group_by_business_key",
    "kingdee_allocate_customers_to_orgs",
    "kingdee_cancel_allocate_customers_to_orgs",
    "kingdee_delete_recent_entity",
]

CHAT_BLOCKING_PATTERNS = [
    "The user wants",
    "The user is asking",
    "I need to",
    "I need",
    "I should",
    "Let me",
    "First,",
    "Actually",
    "According to the rules",
    "Now I",
    "But wait",
    "The same error",
    "looking at the tool",
    "tool returned",
    "I should relay",
    "I should inform",
    "KeyError",
    "Traceback",
    "'acct_id'",
    "用户想",
    "用户要",
    "我需要",
    "我应该",
    "让我",
    "首先",
    "现在我",
    "根据路由规则",
    "根据规则",
    "系统提示",
    "我将这个结果",
    "返回给用户",
]

ACCEPTABLE_ENV_BLOCKERS = [
    "金蝶连接配置不完整",
    "金蝶连接配置未填写",
    "权限尚未配置",
    "无权",
]


def contains_emoji(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (
            0x1F300 <= code <= 0x1FAFF
            or 0x2600 <= code <= 0x27BF
            or code in {0xFE0F, 0x200D}
        ):
            return True
    return False


@dataclass
class UATCase:
    name: str
    category: str
    passed: bool
    status: int | None = None
    duration_ms: int = 0
    detail: str = ""
    request: Any = None
    response: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)


class UATClient:
    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        agent_id: str = "default",
        **kwargs: Any,
    ) -> tuple[int, Any]:
        headers = kwargs.pop("headers", {})
        headers.setdefault("X-Agent-Id", agent_id)
        resp = await self.client.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            **kwargs,
        )
        try:
            data = resp.json()
        except Exception:
            data = resp.text[:4000]
        return resp.status_code, data

    async def chat(
        self,
        text: str,
        *,
        agent_id: str,
        user_id: str,
        channel: str,
        session_id: str | None = None,
    ) -> tuple[int, list[dict[str, Any]], str]:
        session_id = session_id or f"uat-{uuid.uuid4().hex[:12]}"
        body = {
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": text}],
                },
            ],
            "session_id": session_id,
            "user_id": user_id,
            "channel": channel,
        }
        events: list[dict[str, Any]] = []
        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/console/chat",
            json=body,
            headers={"Content-Type": "application/json", "X-Agent-Id": agent_id},
        ) as resp:
            status = resp.status_code
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    continue
        return status, events, extract_text(events)


def extract_text(events: list[dict[str, Any]]) -> str:
    visible_chunks: list[str] = []
    fallback_chunks: list[str] = []
    for event in events:
        if event.get("object") == "content" and event.get("type") == "text":
            text = event.get("text")
            if isinstance(text, str):
                visible_chunks.append(text)
        if event.get("object") == "message":
            content = event.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text" and isinstance(block.get("text"), str):
                            visible_chunks.append(block["text"])
                        elif block.get("type") == "refusal" and isinstance(block.get("refusal"), str):
                            visible_chunks.append(block["refusal"])
            elif isinstance(content, str):
                visible_chunks.append(content)
        for key in ("delta", "content", "message", "output_text"):
            value = event.get(key)
            if isinstance(value, str):
                fallback_chunks.append(value)
    if visible_chunks:
        return "".join(visible_chunks).strip()
    return "".join(fallback_chunks).strip()


def event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    objects = sorted({str(event.get("object")) for event in events if event.get("object")})
    statuses = sorted({str(event.get("status")) for event in events if event.get("status")})
    tool_mentions: list[str] = []
    raw = json.dumps(events, ensure_ascii=False)
    for tool in EXPECTED_ERP_TOOLS + ["chat_with_agent"]:
        if tool in raw:
            tool_mentions.append(tool)
    errors = [
        event.get("error")
        for event in events
        if event.get("error") not in (None, "")
    ]
    return {
        "event_count": len(events),
        "objects": objects,
        "statuses": statuses,
        "tool_mentions": sorted(set(tool_mentions)),
        "errors": errors[:5],
    }


def has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def find_chat_blockers(text: str) -> list[str]:
    lowered = text.lower()
    compact = "".join(lowered.split())
    blockers = []
    for pattern in CHAT_BLOCKING_PATTERNS:
        normalized = pattern.lower()
        compact_pattern = "".join(normalized.split())
        if normalized in lowered or compact_pattern in compact:
            blockers.append(pattern)
    return blockers


async def timed_case(name: str, category: str, fn) -> UATCase:
    started = time.perf_counter()
    try:
        case: UATCase = await fn()
        case.duration_ms = int((time.perf_counter() - started) * 1000)
        return case
    except Exception as exc:
        return UATCase(
            name=name,
            category=category,
            passed=False,
            duration_ms=int((time.perf_counter() - started) * 1000),
            detail=f"{type(exc).__name__}: {exc}",
        )


async def cleanup_permission(client: UATClient, key: str) -> None:
    await client.request("DELETE", f"/api/erp-permissions/{quote(key, safe='')}")


async def run_agent_registration(client: UATClient) -> list[UATCase]:
    results: list[UATCase] = []

    async def list_agents_case() -> UATCase:
        status, data = await client.request("GET", "/api/agents")
        agent_ids = [item.get("id") for item in data.get("agents", [])] if isinstance(data, dict) else []
        missing = [agent for agent in DEFAULT_AGENTS if agent not in agent_ids]
        return UATCase(
            name="Agent 注册列表",
            category="agent_registration",
            passed=status == 200 and not missing,
            status=status,
            detail="全部 ERP Agent 已注册" if not missing else f"缺少 Agent: {missing}",
            request={"method": "GET", "path": "/api/agents"},
            response=data,
            evidence={"agent_ids": agent_ids},
        )

    results.append(await timed_case("Agent 注册列表", "agent_registration", list_agents_case))

    for agent_id in DEFAULT_AGENTS:
        async def tools_case(agent_id: str = agent_id) -> UATCase:
            status, data = await client.request("GET", f"/api/agents/{agent_id}/tools", agent_id=agent_id)
            tools = data if isinstance(data, list) else []
            names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
            enabled = [tool.get("name") for tool in tools if isinstance(tool, dict) and tool.get("enabled")]
            erp_enabled = [name for name in enabled if isinstance(name, str) and (name.startswith("kingdee_") or name.startswith("erp_"))]
            erp_descriptions = " ".join(
                str(tool.get("description", "")) + " " + str(tool.get("icon", ""))
                for tool in tools
                if (
                    isinstance(tool, dict)
                    and tool.get("enabled")
                    and isinstance(tool.get("name"), str)
                    and (
                        tool["name"].startswith("kingdee_")
                        or tool["name"].startswith("erp_")
                    )
                )
            )
            if agent_id == "default":
                passed = status == 200 and "chat_with_agent" in names
                detail = "默认 Agent 具备路由工具" if passed else "默认 Agent 未暴露 chat_with_agent 路由工具"
            else:
                missing = [tool for tool in EXPECTED_ERP_TOOLS if tool not in enabled]
                passed = status == 200 and not missing and not contains_emoji(erp_descriptions)
                detail = "ERP 工具完整启用且描述无表情符号"
                if missing:
                    detail = f"缺少或未启用 ERP 工具: {missing}"
                elif contains_emoji(erp_descriptions):
                    detail = "工具描述或图标包含表情符号"
            return UATCase(
                name=f"{agent_id} 工具注册",
                category="agent_registration",
                passed=passed,
                status=status,
                detail=detail,
                request={"method": "GET", "path": f"/api/agents/{agent_id}/tools"},
                response={"tool_count": len(names), "erp_enabled_count": len(erp_enabled)},
                evidence={"enabled_erp_tools": erp_enabled, "tool_names_sample": names[:20]},
            )

        results.append(await timed_case(f"{agent_id} 工具注册", "agent_registration", tools_case))

    return results


async def run_permission_api(client: UATClient, user_id: str, channel: str) -> list[UATCase]:
    results: list[UATCase] = []
    key = f"{channel}:{user_id}"
    await cleanup_permission(client, key)
    for agent_id in ("erp-sales", "erp-purchase"):
        await client.request(
            "DELETE",
            f"/api/erp-permissions/org-context?channel={channel}&user_id={user_id}&agent_id={agent_id}",
            agent_id=agent_id,
        )

    async def create_permission_case() -> UATCase:
        bodies = [
            {
                "key": key,
                "org_id": "100",
                "display_name": "UAT 用户组织 100",
                "domains": ["sales", "purchase", "inventory", "finance"],
                "role": "admin",
                "operations": [
                    "query",
                    "save",
                    "delete",
                    "submit",
                    "audit",
                    "unaudit",
                    "push",
                    "allocate",
                    "execute",
                    "workflow",
                ],
            },
            {
                "key": key,
                "org_id": "200",
                "display_name": "UAT 用户组织 200",
                "domains": ["sales", "purchase"],
                "role": "operator",
                "operations": ["query", "save", "allocate"],
            },
        ]
        statuses = []
        responses = []
        for body in bodies:
            status, data = await client.request("POST", "/api/erp-permissions/", json=body)
            statuses.append(status)
            responses.append(data)
        passed = all(status == 200 for status in statuses)
        return UATCase(
            name="权限创建",
            category="permission_api",
            passed=passed,
            status=statuses[-1] if statuses else None,
            detail="已为 UAT 用户创建两个组织权限" if passed else f"状态码: {statuses}",
            request=bodies,
            response=responses,
        )

    async def list_permission_case() -> UATCase:
        status, data = await client.request("GET", f"/api/erp-permissions/{quote(key, safe='')}")
        items = data.get("items", []) if isinstance(data, dict) else []
        orgs = sorted(item.get("org_id") for item in items)
        passed = status == 200 and "100" in orgs and "200" in orgs
        return UATCase(
            name="权限查询",
            category="permission_api",
            passed=passed,
            status=status,
            detail=f"查询到组织权限: {orgs}",
            request={"method": "GET", "key": key},
            response=data,
        )

    async def operations_case() -> UATCase:
        status, data = await client.request("GET", f"/api/erp-permissions/{quote(key, safe='')}/operations?org_id=100&domain=sales")
        operations = data.get("operations", []) if isinstance(data, dict) else []
        passed = status == 200 and {"query", "save", "delete", "allocate"}.issubset(set(operations))
        return UATCase(
            name="用户操作权限查询",
            category="permission_api",
            passed=passed,
            status=status,
            detail=f"sales/100 操作码: {operations}",
            request={"method": "GET", "path": f"/api/erp-permissions/{key}/operations"},
            response=data,
        )

    async def org_context_isolation_case() -> UATCase:
        requests = [
            ("erp-sales", "100"),
            ("erp-purchase", "200"),
        ]
        responses = []
        for agent_id, org_id in requests:
            status, data = await client.request(
                "PUT",
                "/api/erp-permissions/org-context",
                agent_id=agent_id,
                json={
                    "org_id": org_id,
                    "channel": channel,
                    "user_id": user_id,
                    "agent_id": agent_id,
                },
            )
            responses.append({"agent_id": agent_id, "status": status, "data": data})
        reads = []
        for agent_id, _ in requests:
            status, data = await client.request(
                "GET",
                f"/api/erp-permissions/org-context?channel={channel}&user_id={user_id}&agent_id={agent_id}",
                agent_id=agent_id,
            )
            reads.append({"agent_id": agent_id, "status": status, "data": data})
        by_agent = {item["agent_id"]: str(item["data"].get("org_id", "")) for item in reads if isinstance(item.get("data"), dict)}
        passed = by_agent.get("erp-sales") == "100" and by_agent.get("erp-purchase") == "200"
        return UATCase(
            name="默认组织按 Agent 隔离",
            category="permission_api",
            passed=passed,
            status=200 if passed else None,
            detail=f"读取结果: {by_agent}",
            request=requests,
            response={"writes": responses, "reads": reads},
            evidence={"org_by_agent": by_agent},
        )

    async def bypass_disabled_case() -> UATCase:
        status, data = await client.request(
            "PUT",
            "/api/erp-permissions/org-context",
            agent_id="erp-sales",
            json={
                "org_id": "999",
                "channel": channel,
                "user_id": user_id,
                "agent_id": "erp-sales",
            },
        )
        text = json.dumps(data, ensure_ascii=False)
        passed = status == 200 and has_any(text, ["无权", "权限", "不允许", "error"])
        return UATCase(
            name="WebUI/Console 默认不绕过未授权组织",
            category="permission_api",
            passed=passed,
            status=status,
            detail="未授权组织被拒绝" if passed else "未授权组织未被拒绝",
            request={"org_id": "999", "channel": channel, "user_id": user_id, "agent_id": "erp-sales"},
            response=data,
        )

    for name, fn in [
        ("权限创建", create_permission_case),
        ("权限查询", list_permission_case),
        ("用户操作权限查询", operations_case),
        ("默认组织按 Agent 隔离", org_context_isolation_case),
        ("WebUI/Console 默认不绕过未授权组织", bypass_disabled_case),
    ]:
        results.append(await timed_case(name, "permission_api", fn))

    return results


CHAT_CASES = [
    {
        "name": "默认 Agent 销售路由",
        "agent_id": "default",
        "session": "route-sales",
        "prompt": "查询最近 3 条销售订单，列出单号、客户、日期。",
        "keywords": ["erp-sales", "销售", "chat_with_agent", "权限", "组织", "金蝶"],
    },
    {
        "name": "默认 Agent 采购路由",
        "agent_id": "default",
        "session": "route-purchase",
        "prompt": "查询最近 3 条采购订单，列出单号、供应商、日期。",
        "keywords": ["erp-purchase", "采购", "chat_with_agent", "权限", "组织", "金蝶"],
    },
    {
        "name": "默认 Agent 库存路由",
        "agent_id": "default",
        "session": "route-inventory",
        "prompt": "查询物料 M001 的即时库存。",
        "keywords": ["erp-inventory", "库存", "chat_with_agent", "权限", "组织", "金蝶"],
    },
    {
        "name": "销售 Agent 查询闭环",
        "agent_id": "erp-sales",
        "session": "sales-query",
        "prompt": "查询最近 3 条销售订单，列出单号、客户、日期。",
        "keywords": ["SAL_SaleOrder", "销售", "组织", "权限", "配置", "查询"],
    },
    {
        "name": "采购 Agent 新增供应商预览",
        "agent_id": "erp-purchase",
        "session": "supplier-flow",
        "prompt": "新增一个供应商，编码 UAT-SUP-001，名称 UAT测试供应商。",
        "keywords": ["写入操作预览", "预览", "execute=True", "确认", "BD_Supplier", "供应商"],
    },
    {
        "name": "采购 Agent 刚新增错了删除闭环",
        "agent_id": "erp-purchase",
        "session": "supplier-flow",
        "prompt": "刚才供应商建错了，删掉吧。",
        "keywords": ["删除", "预览", "刚才", "最近", "未找到", "确认", "execute=True"],
    },
    {
        "name": "销售 Agent 客户分组下级新增",
        "agent_id": "erp-sales",
        "session": "group-flow",
        "prompt": "新增客户分组，编码 UAT-GROUP-01，名称 UAT华东客户，放在国内客户下级。",
        "keywords": ["kingdee_create_group_under_parent", "分组", "QueryGroupInfo", "GroupSave", "父分组", "预览", "国内客户"],
    },
    {
        "name": "销售 Agent 客户分组编码消歧",
        "agent_id": "erp-sales",
        "session": "group-flow",
        "prompt": "父分组编码是 CN-CUST，请新增客户分组，编码 UAT-GROUP-02，名称 UAT华南客户，放在这个分组下级。",
        "keywords": ["分组编码", "CN-CUST", "GroupSave", "预览", "父分组"],
    },
    {
        "name": "销售 Agent 客户分组查询",
        "agent_id": "erp-sales",
        "session": "group-query",
        "prompt": "查询客户分组编码 UAT-GROUP-01 的分组信息。",
        "keywords": ["kingdee_query_group_by_business_key", "QueryGroupInfo", "分组", "UAT-GROUP-01", "查询"],
    },
    {
        "name": "销售 Agent 客户分组删除预览",
        "agent_id": "erp-sales",
        "session": "group-delete",
        "prompt": "删除客户分组编码 UAT-GROUP-01。",
        "keywords": ["GroupDelete", "删除", "分组", "预览", "execute=True", "确认"],
    },
    {
        "name": "销售 Agent 客户分配预览",
        "agent_id": "erp-sales",
        "session": "allocate-flow",
        "prompt": "把客户编码 CUST001 分配到组织 200。",
        "keywords": ["Allocate", "分配", "客户", "组织", "预览", "execute=True", "CUST001"],
    },
    {
        "name": "销售 Agent 客户取消分配预览",
        "agent_id": "erp-sales",
        "session": "cancel-allocate-flow",
        "prompt": "取消客户编码 CUST001 分配到组织 200。",
        "keywords": ["CancelAllocate", "取消分配", "客户", "组织", "预览", "execute=True", "CUST001"],
    },
    {
        "name": "非法 FormId 防幻觉",
        "agent_id": "erp-sales",
        "session": "invalid-form",
        "prompt": "查询 BAD_FORM 的数据。",
        "keywords": ["不合法", "BAD_FORM", "kingdee_search_form", "不存在", "FormId"],
    },
]


async def run_chat_cases(client: UATClient, user_id: str, channel: str) -> list[UATCase]:
    results: list[UATCase] = []
    session_prefix = f"uat-{datetime.now().strftime('%H%M%S')}"
    session_ids: dict[str, str] = {}

    for spec in CHAT_CASES:
        async def chat_case(spec: dict[str, Any] = spec) -> UATCase:
            session_key = spec["session"]
            session_id = session_ids.setdefault(session_key, f"{session_prefix}-{session_key}")
            status, events, text = await client.chat(
                spec["prompt"],
                agent_id=spec["agent_id"],
                user_id=user_id,
                channel=channel,
                session_id=session_id,
            )
            summary = event_summary(events)
            text_or_raw = text or json.dumps(events[-3:], ensure_ascii=False)
            matched = has_any(text_or_raw, spec["keywords"]) or bool(set(summary["tool_mentions"]) & set(EXPECTED_ERP_TOOLS + ["chat_with_agent"]))
            env_blocked = has_any(text_or_raw, ACCEPTABLE_ENV_BLOCKERS)
            blockers = find_chat_blockers(text_or_raw)
            completed = "completed" in summary["statuses"] or status == 200
            passed = (
                status == 200
                and completed
                and (matched or env_blocked)
                and not summary["errors"]
                and not blockers
            )
            return UATCase(
                name=spec["name"],
                category="chat_api",
                passed=passed,
                status=status,
                detail=(
                    "聊天接口返回符合业务闭环预期"
                    if passed
                    else "未观察到预期关键词、存在内部推理泄漏或裸异常"
                ),
                request={
                    "agent_id": spec["agent_id"],
                    "session_id": session_id,
                    "user_id": user_id,
                    "channel": channel,
                    "prompt": spec["prompt"],
                    "expected_keywords": spec["keywords"],
                },
                response=text_or_raw[:4000],
                evidence={**summary, "blocking_patterns": blockers, "environment_blocked": env_blocked},
            )

        results.append(await timed_case(spec["name"], "chat_api", chat_case))

    return results


async def run(base_url: str, timeout: int) -> dict[str, Any]:
    client = UATClient(base_url, timeout)
    user_id = f"uat-user-{uuid.uuid4().hex[:8]}"
    channel = "console"
    results: list[UATCase] = []
    started = time.perf_counter()
    try:
        results.extend(await run_agent_registration(client))
        results.extend(await run_permission_api(client, user_id, channel))
        results.extend(await run_chat_cases(client, user_id, channel))
    finally:
        await client.close()

    total = len(results)
    passed = sum(1 for item in results if item.passed)
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "user_id": user_id,
        "channel": channel,
        "duration_seconds": round(time.perf_counter() - started, 1),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / max(total, 1) * 100, 1),
        "results": [item.__dict__ for item in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="金蝶 ERP Agent UAT")
    parser.add_argument("--base-url", default="http://127.0.0.1:8089")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", default="docs/uat_erp_chat_permissions_results.json")
    args = parser.parse_args()

    data = asyncio.run(run(args.base_url, args.timeout))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"UAT 完成: {data['passed']}/{data['total']} 通过，耗时 {data['duration_seconds']}s")
    print(f"结果文件: {output}")
    if data["failed"]:
        print("失败项:")
        for item in data["results"]:
            if not item["passed"]:
                print(f"- [{item['category']}] {item['name']}: {item['detail']}")


if __name__ == "__main__":
    main()
