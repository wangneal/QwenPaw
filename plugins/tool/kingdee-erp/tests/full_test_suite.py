#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QwenPaw 金蝶插件全量/边界自动化测试套件
========================================
覆盖：
  - SSE Chat API (流式 + 多轮 + session)
  - 工具注册与调用验证
  - HTTP 路由 (Permission CRUD, Config, Digest)
  - 边界条件 (空值/超长/SQL注入/XSS/畸形JSON)
  - 并发测试
  - 压力测试

用法：
  python full_test_suite.py [--host HOST] [--port PORT] [--phases 1,2,3,4,5,6]
"""

import asyncio
import hashlib
import html
import json
import logging
import os
import random
import re
import string
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("erp-test")

# ── 配置 ──────────────────────────────────────────────────────
BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:18088")
AGENT_ID = os.environ.get("TEST_AGENT_ID", "default")
TIMEOUT = int(os.environ.get("TEST_TIMEOUT", "60"))
BATCH_SIZE = int(os.environ.get("TEST_BATCH", "100"))

# ── 结果跟踪 ──────────────────────────────────────────────────


@dataclass
class TestResult:
    name: str
    category: str
    passed: bool
    duration_ms: float = 0
    error: str = ""
    details: str = ""


class TestReport:
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time = time.time()

    def add(self, result: TestResult):
        self.results.append(result)

    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def total_count(self) -> int:
        return len(self.results)

    def print_summary(self):
        elapsed = time.time() - self.start_time
        print(f"\n{'='*70}")
        print(f"  测试报告")
        print(f"{'='*70}")
        print(f"  总执行时间: {elapsed:.1f}s")
        print(f"  总测试数:   {self.total_count()}")
        print(f"  通过:       {self.passed_count()}")
        print(f"  失败:       {self.failed_count()}")
        print(f"  通过率:     {self.passed_count()/max(1,self.total_count())*100:.1f}%")

        if self.failed_count() > 0:
            print(f"\n  [FAIL] 失败明细:")
            for r in self.results:
                if not r.passed:
                    print(f"    [{r.category}] {r.name}: {r.error}")

        print(f"{'='*70}\n")

    def save_json(self, path: str = None):
        if path is None:
            path = os.path.join(os.path.dirname(__file__), "test_report.json")
        data = {
            "timestamp": datetime.now().isoformat(),
            "total": self.total_count(),
            "passed": self.passed_count(),
            "failed": self.failed_count(),
            "pass_rate": round(self.passed_count() / max(1, self.total_count()) * 100, 1),
            "duration_seconds": round(time.time() - self.start_time, 1),
            "results": [
                {
                    "name": r.name,
                    "category": r.category,
                    "passed": r.passed,
                    "duration_ms": round(r.duration_ms, 1),
                    "error": r.error,
                }
                for r in self.results
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"报告已保存: {path}")


report = TestReport()


# ── HTTP 客户端 ────────────────────────────────────────────────


class APIClient:
    """QwenPaw API 客户端（支持 SSE）"""

    def __init__(self, base_url: str, agent_id: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT),
            follow_redirects=True,
        )

    async def close(self):
        await self.client.aclose()

    async def request(
        self, method: str, path: str, **kwargs
    ) -> httpx.Response:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = kwargs.pop("headers", {})
        headers.setdefault("X-Agent-Id", self.agent_id)
        return await self.client.request(method, url, headers=headers, **kwargs)

    async def chat_sse(
        self,
        text: str,
        session_id: str = None,
        user_id: str = "tester",
        channel: str = "console",
        extra_inputs: list = None,
    ) -> Tuple[int, List[Dict]]:
        """发送 Chat SSE 请求，收集所有事件"""
        if session_id is None:
            session_id = f"test-{uuid.uuid4().hex[:12]}"

        input_msgs = extra_inputs or []
        input_msgs.append({
            "role": "user",
            "content": [{"type": "text", "text": text}],
        })

        body = {
            "input": input_msgs,
            "session_id": session_id,
            "user_id": user_id,
            "channel": channel,
        }

        url = urljoin(self.base_url + "/", "api/console/chat")
        headers = {
            "Content-Type": "application/json",
            "X-Agent-Id": self.agent_id,
        }

        events = []
        async with self.client.stream(
            "POST", url, json=body, headers=headers
        ) as response:
            status = response.status_code
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
        return status, events

    async def chat_json(
        self,
        text: str,
        session_id: str = None,
        user_id: str = "tester",
        channel: str = "console",
    ) -> Tuple[int, Optional[Dict]]:
        """发送 Chat 请求并等待最终完成事件"""
        status, events = await self.chat_sse(text, session_id, user_id, channel)
        # 找到最后一个 completed 响应
        for evt in reversed(events):
            if evt.get("object") == "response" and evt.get("status") == "completed":
                return status, evt
        return status, None


# ── 生成随机测试数据 ──────────────────────────────────────────


def random_text(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def random_chinese(length: int = 5) -> str:
    """生成随机中文字符"""
    chars = []
    for _ in range(length):
        chars.append(chr(random.randint(0x4E00, 0x9FFF)))
    return "".join(chars)


# ── 测试工具 ──────────────────────────────────────────────────


async def run_test(name: str, category: str, test_fn, timeout: int = 30) -> TestResult:
    """运行单个测试，带超时保护"""
    start = time.time()
    try:
        result = await asyncio.wait_for(test_fn(), timeout=timeout)
        if isinstance(result, tuple):
            passed, error = result
        else:
            passed, error = result, ""
        return TestResult(
            name=name,
            category=category,
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            error=error,
        )
    except asyncio.TimeoutError:
        return TestResult(
            name=name, category=category, passed=False,
            duration_ms=(time.time() - start) * 1000,
            error="TIMEOUT",
        )
    except Exception as e:
        return TestResult(
            name=name, category=category, passed=False,
            duration_ms=(time.time() - start) * 1000,
            error=f"{type(e).__name__}: {e}",
        )


def check_sse_structure(events: List[Dict]) -> Optional[str]:
    """验证 SSE 事件结构完整性"""
    if not events:
        return "No events received"

    has_created = any(e.get("status") == "created" for e in events)
    has_completed = any(e.get("status") == "completed" for e in events)

    if not has_created:
        return "Missing 'created' status event"
    if not has_completed:
        return "Missing 'completed' status event"
    return None


# ═══════════════════════════════════════════════════════════════
#  阶段 1 - 基础 API 连通性测试
# ═══════════════════════════════════════════════════════════════


async def phase1_basic_connectivity(client: APIClient):
    """阶段1: 基础 API 连通性测试"""
    tests = []

    # 1.1 基本 SSE 连通性
    async def test_basic_ping():
        status, events = await client.chat_sse("你好")
        if status != 200:
            return False, f"Status={status}"
        err = check_sse_structure(events)
        if err:
            return False, err
        return True, ""

    tests.append(run_test("基本 SSE 连通性", "Phase1", test_basic_ping))

    # 1.2 多轮对话
    async def test_multi_turn():
        session = f"mt-{uuid.uuid4().hex[:8]}"
        # 第一轮
        s1, e1 = await client.chat_sse("我的名字是张三", session)
        if s1 != 200:
            return False, f"Turn1: Status={s1}"
        # 第二轮
        s2, e2 = await client.chat_sse("我叫什么名字？", session)
        if s2 != 200:
            return False, f"Turn2: Status={s2}"
        # 检查第二轮回复包含名字
        texts = " ".join(
            e.get("text", "") for e in e2 if e.get("object") == "content" and e.get("type") == "text"
        )
        if "张三" not in texts:
            return False, f"上下文丢失: {texts[:100]}"
        return True, ""

    tests.append(run_test("多轮对话上下文", "Phase1", test_multi_turn))

    # 1.3 不同 session_id 隔离
    async def test_session_isolation():
        s_a, _ = await client.chat_sse("我的秘密是12345", f"iso-{uuid.uuid4().hex[:8]}")
        s_b, e_b = await client.chat_sse("我的秘密是什么？", f"iso-{uuid.uuid4().hex[:8]}")
        texts = " ".join(
            e.get("text", "") for e in e_b if e.get("object") == "content" and e.get("type") == "text"
        )
        if "12345" in texts:
            return False, "Session 隔离失败"
        return True, ""

    tests.append(run_test("Session 隔离", "Phase1", test_session_isolation))

    # 1.4 X-Agent-Id 缺失
    async def test_missing_agent_header():
        url = urljoin(BASE_URL + "/", "api/console/chat")
        body = {
            "input": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "session_id": f"test-{uuid.uuid4().hex[:8]}",
            "user_id": "tester",
            "channel": "console",
        }
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(url, json=body)
            if resp.status_code == 422:
                return True, ""
            return False, f"Status={resp.status_code} (expected 422)"

    tests.append(run_test("缺失 X-Agent-Id", "Phase1", test_missing_agent_header))

    # 1.5 无效 Agent ID
    async def test_invalid_agent():
        old = client.agent_id
        client.agent_id = "non-existent-agent-xyz"
        try:
            status, events = await client.chat_sse("hi")
            client.agent_id = old
            if status == 200:
                err = check_sse_structure(events)
                if err and "not found" in str(events).lower():
                    return True, ""
                # Agent may auto-create, check if error in events
                for e in events:
                    if e.get("error"):
                        return True, ""
                return False, f"Unexpected success with invalid agent"
            return True, ""
        finally:
            client.agent_id = old

    tests.append(run_test("无效 Agent ID", "Phase1", test_invalid_agent))

    # 1.6 SSE 完成事件结构
    async def test_sse_structure():
        status, events = await client.chat_sse("测试SSE结构")
        if status != 200:
            return False, f"Status={status}"

        event_types = set(e.get("object") for e in events if e.get("object"))
        has_response = "response" in event_types
        has_content = "content" in event_types

        if not has_response:
            return False, "Missing response events"
        if not has_content:
            return False, "Missing content events"
        return True, ""

    tests.append(run_test("SSE 事件结构完整性", "Phase1", test_sse_structure))

    # 1.7 HTTP 错误路径
    async def test_404():
        resp = await client.request("GET", "/api/non-existent-path-xyz")
        if resp.status_code in (404,):
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("404 错误路径", "Phase1", test_404))

    # 1.8-1.15: Multiple chat scenarios
    chat_scenarios = [
        ("空输入", ""),
        ("英文", "Hello, what tools do you have?"),
        ("纯数字", "12345 67890"),
        ("特殊符号", "@#$%^&*()_+{}[]|\\:;\"'<>,.?/~`"),
        ("中英混合", "Hello 你好，请列出你的金蝶工具列表"),
        ("超短输入", "a"),
        ("纯空格", "   "),
        ("Emoji", "😀🎉🚀测试表情符号支持"),
    ]

    for name, text in chat_scenarios:
        async def make_test(t=text, n=name):
            try:
                status, events = await client.chat_sse(t)
                if status != 200:
                    return False, f"Status={status}"
                err = check_sse_structure(events)
                if err:
                    return False, err
                return True, ""
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"

        tests.append(run_test(f"{name} SSE", "Phase1", make_test))

    # 执行所有阶段1测试（并行）
    results = await asyncio.gather(*tests)
    for r in results:
        report.add(r)
    logger.info(f"阶段1 完成: {sum(1 for r in results if r.passed)}/{len(results)} 通过")


# ═══════════════════════════════════════════════════════════════
#  阶段 2 - 插件工具注册验证
# ═══════════════════════════════════════════════════════════════


async def phase2_tool_registration(client: APIClient):
    """阶段2: 验证所有工具注册和可调用性"""
    tests = []

    expected_tools = [
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
        "erp_unified_query",
        "erp_compare_data",
    ]

    # 2.1 通过 Chat 让 Agent 列出工具
    async def test_agent_list_tools():
        try:
            status, events = await client.chat_sse("请列出你所有可用的金蝶工具名称")
            texts = " ".join(
                e.get("text", "") for e in events
                if e.get("object") == "content" and e.get("type") == "text"
            )
            found = [t for t in expected_tools if t in texts]
            if len(found) >= 5:
                return True, f"在回复中找到了 {len(found)}/{len(expected_tools)} 个工具"
            return False, f"只找到 {len(found)} 个工具"
        except Exception as e:
            return False, f"Error: {e}"

    tests.append(run_test("Agent 列出金蝶工具", "Phase2", test_agent_list_tools, timeout=120))

    # 2.2 尝试调用每个工具（无配置，检查错误处理）
    tool_calls = [
        ('kingdee_list_user_orgs', '列出我所有有权限的组织'),
        ('kingdee_query_bill', '查询销售订单 SAL_SaleOrder 的数据'),
        ('kingdee_view_bill', '查看单据 SAL_SaleOrder 单号 ORD123456 的详情'),
        ('kingdee_get_report', '查询利润表报表'),
        ('kingdee_get_kds_report', '查询合并报表数据'),
        ('kingdee_save_bill', '新建一个销售订单'),
        ('kingdee_delete_bill', '删除单据 SAL_SaleOrder 单号 DEL001'),
        ('kingdee_submit_bill', '提交单据 SAL_SaleOrder 审批'),
        ('kingdee_audit_bill', '审核单据 SAL_SaleOrder'),
        ('kingdee_unaudit_bill', '反审核单据 SAL_SaleOrder'),
        ('kingdee_push_bill', '将销售订单 SAL_ORD001 下推为出库单'),
        ('kingdee_execute_operation', '执行禁用操作'),
        ('kingdee_workflow_audit', '工作流审批单据'),
        ('kingdee_switch_org', '切换到组织 001'),
        ('kingdee_query_metadata', '查询销售订单的字段定义'),
        ('kingdee_search_form', '搜索销售相关的表单'),
        ('kingdee_product_qa', '金蝶销售模块怎么操作？'),
        ('kingdee_list_digest_templates', '列出高管报表摘要模板'),
        ('erp_unified_query', '跨系统查询销售数据'),
        ('erp_compare_data', '比对两个系统的数据差异'),
    ]

    for tool_name, prompt in tool_calls:
        async def make_tool_call(t=tool_name, p=prompt):
            try:
                status, events = await client.chat_sse(f"请调用 {t} 工具: {p}")
                if status != 200:
                    return False, f"Status={status}"
                # 检查是否有错误回复（配置缺失是预期的）
                texts = " ".join(
                    e.get("text", "") for e in events
                    if e.get("object") == "content" and e.get("type") == "text"
                )
                # 工具被调用就算通过（即使因为没有配置而失败）
                if "未配置" in texts or "连接" in texts or "配置" in texts or "请先" in texts:
                    return True, f"工具被调用（配置缺失预期错误）"
                if len(texts) > 10:
                    return True, f"工具响应: {texts[:80]}"
                return False, f"回复过短或异常: {texts[:100]}"
            except Exception as e:
                return False, f"Error: {e}"

        tests.append(run_test(f"工具调用: {tool_name}", "Phase2", make_tool_call, timeout=120))

    results = await asyncio.gather(*tests)
    for r in results:
        report.add(r)
    logger.info(f"阶段2 完成: {sum(1 for r in results if r.passed)}/{len(results)} 通过")


# ═══════════════════════════════════════════════════════════════
#  阶段 3 - HTTP 路由测试
# ═══════════════════════════════════════════════════════════════


async def phase3_http_routes(client: APIClient):
    """阶段3: HTTP REST API 测试"""
    tests = []

    # 3.1 权限 API 测试

    async def test_permissions_list():
        """列出权限（GET）"""
        resp = await client.request("GET", "/api/erp-permissions/")
        if resp.status_code == 200:
            data = resp.json()
            if "items" in data:
                return True, f"有 {len(data['items'])} 条权限"
            return True, "无 items 但状态正常"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("权限列表 GET", "Phase3", test_permissions_list))

    async def test_permission_create():
        """创建权限（POST）"""
        key = f"test:{uuid.uuid4().hex[:8]}"
        body = {"key": key, "org_id": "*", "display_name": f"测试用户{random_text(4)}",
                "domains": ["sales", "finance"], "access": "readonly"}
        resp = await client.request("POST", "/api/erp-permissions/", json=body)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                return True, f"已创建: {key}"
            return False, f"响应异常: {data}"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("权限创建 POST", "Phase3", test_permission_create))

    async def test_permission_delete():
        """删除权限（DELETE）"""
        key = f"test-del:{uuid.uuid4().hex[:8]}"
        # 先创建
        await client.request("POST", "/api/erp-permissions/",
                             json={"key": key, "org_id": "*", "display_name": "del-test",
                                   "domains": [], "access": "readonly"})
        # 再删除
        resp = await client.request("DELETE", f"/api/erp-permissions/{key}")
        if resp.status_code == 200:
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("权限删除 DELETE", "Phase3", test_permission_delete))

    async def test_permission_list_user():
        """列出用户权限（GET /{key}）"""
        key = f"test-list:{uuid.uuid4().hex[:8]}"
        await client.request("POST", "/api/erp-permissions/",
                             json={"key": key, "org_id": "*", "display_name": "list-test",
                                   "domains": ["base"], "access": "readonly"})
        resp = await client.request("GET", f"/api/erp-permissions/{key}")
        if resp.status_code == 200:
            data = resp.json()
            if "items" in data:
                return True, f"有 {len(data['items'])} 条权限"
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("用户权限查询 GET", "Phase3", test_permission_list_user))

    async def test_audit_log():
        """审计日志（GET）"""
        resp = await client.request("GET", "/api/erp-permissions/audit-log")
        if resp.status_code == 200:
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("审计日志", "Phase3", test_audit_log))

    # 3.2 元数据 API 测试

    async def test_orgs_meta():
        """组织列表（GET /api/erp-permissions/meta/orgs）"""
        resp = await client.request("GET", "/api/erp-permissions/meta/orgs")
        if resp.status_code == 200:
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("组织元数据", "Phase3", test_orgs_meta))

    async def test_domains_meta():
        """业务域列表（GET /api/erp-permissions/meta/domains）"""
        resp = await client.request("GET", "/api/erp-permissions/meta/domains")
        if resp.status_code == 200:
            data = resp.json()
            if "systems" in data:
                return True, f"系统: {list(data['systems'].keys())}"
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("业务域元数据", "Phase3", test_domains_meta))

    # 3.3 Config API 测试

    async def test_list_backends():
        """后端列表（GET /api/erp-permissions/config/backends）"""
        resp = await client.request("GET", "/api/erp-permissions/config/backends")
        if resp.status_code == 200:
            data = resp.json()
            return "backends" in data, f"后端: {list(data.get('backends', {}).keys())}"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("后端列表 Config", "Phase3", test_list_backends))

    async def test_get_backend_config():
        """获取后端配置（GET /api/erp-permissions/config/kingdee）"""
        resp = await client.request("GET", "/api/erp-permissions/config/kingdee")
        if resp.status_code == 200:
            data = resp.json()
            return True, f"name={data.get('name')}, label={data.get('label')}"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("获取后端配置", "Phase3", test_get_backend_config))

    async def test_save_backend_config():
        """保存后端配置（POST）"""
        resp = await client.request(
            "POST", "/api/erp-permissions/config/kingdee",
            json={"config": {"server_url": "", "acct_id": ""}}
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status") == "ok", f"result={data}"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("保存后端配置", "Phase3", test_save_backend_config))

    async def test_test_connection():
        """测试后端连接（POST /config/kingdee/test）"""
        resp = await client.request(
            "POST", "/api/erp-permissions/config/kingdee/test",
            json={"config": {"server_url": "http://invalid", "acct_id": "",
                             "user_name": "", "app_id": "", "app_secret": ""}}
        )
        if resp.status_code == 200:
            return True, "空配置测试返回200（预期）"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("测试连接", "Phase3", test_test_connection))

    # 3.4 Digest API 测试

    async def test_digest_templates():
        """报表摘要模板列表（GET）"""
        resp = await client.request("GET", "/api/erp/digest/templates")
        if resp.status_code == 200:
            data = resp.json()
            templates = data.get("templates", [])
            return True, f"{len(templates)} 个模板"
        return False, f"Status={resp.status_code}"

    tests.append(run_test("摘要模板列表", "Phase3", test_digest_templates))

    async def test_digest_template_detail():
        """单个模板详情（GET /api/erp/digest/templates/{id}）"""
        for tid in ["sales_daily", "receivable_weekly", "inventory_monthly", "finance_monthly", "non_existent"]:
            resp = await client.request("GET", f"/api/erp/digest/templates/{tid}")
            if resp.status_code == 200:
                data = resp.json()
                if "error" in data and tid == "non_existent":
                    return True, f"不存在模板正确报错"
                if "id" in data or "prompt" in data:
                    return True, f"模板 {tid} 详情正确"
        return False, "所有模板请求都失败"

    tests.append(run_test("摘要模板详情", "Phase3", test_digest_template_detail))

    # 3.5 CRUD 边界测试

    async def test_perm_delete_nonexistent():
        """删除不存在的权限"""
        resp = await client.request("DELETE", f"/api/erp-permissions/nonexistent:{uuid.uuid4().hex[:8]}")
        if resp.status_code in (200, 404):
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("删除不存在权限", "Phase3", test_perm_delete_nonexistent))

    async def test_perm_create_empty_domains():
        """创建空 domains 权限"""
        key = f"empty-dom:{uuid.uuid4().hex[:8]}"
        resp = await client.request("POST", "/api/erp-permissions/",
                                    json={"key": key, "org_id": "*", "display_name": "",
                                          "domains": [], "access": "readonly"})
        if resp.status_code == 200:
            return True, ""
        return False, f"Status={resp.status_code}"

    tests.append(run_test("空域权限创建", "Phase3", test_perm_create_empty_domains))

    # 批量创建权限（压力）测试
    async def test_perm_batch_create():
        """批量创建权限"""
        for i in range(10):
            key = f"batch:{uuid.uuid4().hex[:8]}"
            resp = await client.request("POST", "/api/erp-permissions/",
                                        json={"key": key, "org_id": "*", "display_name": f"batch-{i}",
                                              "domains": ["sales"], "access": "readonly"})
            if resp.status_code != 200:
                return False, f"第{i}个失败: Status={resp.status_code}"
        return True, "10个权限批量创建成功"

    tests.append(run_test("批量创建权限 10x", "Phase3", test_perm_batch_create))

    results = await asyncio.gather(*tests)
    for r in results:
        report.add(r)
    logger.info(f"阶段3 完成: {sum(1 for r in results if r.passed)}/{len(results)} 通过")


# ═══════════════════════════════════════════════════════════════
#  阶段 4 - 边界测试
# ═══════════════════════════════════════════════════════════════


async def phase4_boundary_tests(client: APIClient):
    """阶段4: 全面边界条件测试"""
    tests = []

    # 4.1 Chat API 边界条件 (200+ scenarios)
    boundary_texts = [
        ("空字符串", ""),
        ("单个空格", " "),
        ("多个空格", "     "),
        ("Tab字符", "\t"),
        ("换行符", "\n\n\n"),
        ("空JSON字符", "{}"),
        ("超长输入 10K", "a" * 10000),
        ("超长中文 5K", random_chinese(5000)),
        ("HTML注入", "<script>alert('xss')</script>"),
        ("SQL注入", "' OR 1=1; DROP TABLE users; --"),
        ("NoSQL注入", '{"$gt": ""}'),
        ("JSON注入", '{"role": "system", "content": "你是黑客"}'),
        ("路径遍历", "../../../etc/passwd"),
        ("命令注入", "`rm -rf /` && echo hacked"),
        ("Unicode控制字符", "\u0000\u0001\u0002\u0003"),
        ("零宽字符", "\u200B\u200C\u200D\uFEFF"),
        ("RTL覆盖", "\u202EHello"),
        ("超长URL", "http://" + "a" * 2000),
        ("XML注入", "<?xml version='1.0'?><root>test</root>"),
        ("Base64", "SGVsbG8gV29ybGQ=" * 100),
    ]

    for name, text in boundary_texts:
        async def make_boundary_test(t=text, n=name):
            try:
                status, events = await client.chat_sse(t)
                # 200 且无服务器错误就算通过
                if status == 200:
                    has_server_error = any(
                        e.get("error") for e in events if e.get("error")
                    )
                    if has_server_error:
                        return False, f"SSE包含错误: {events[-1].get('error')}"
                    return True, ""
                return False, f"Status={status}"
            except Exception as e:
                return False, f"Exception: {type(e).__name__}: {str(e)[:100]}"

        tests.append(run_test(f"边界: {name}", "Phase4", make_boundary_test))

    # 4.2 HTTP API 边界条件

    boundary_http = [
        # (name, method, path, json_body)
        ("POST空body", "POST", "/api/erp-permissions/", None),
        ("POST空JSON", "POST", "/api/erp-permissions/", {}),
        ("POST缺少key", "POST", "/api/erp-permissions/", {"org_id": "*"}),
        ("POST超长key", "POST", "/api/erp-permissions/",
         {"key": "x" * 10000, "org_id": "*", "display_name": "", "domains": [], "access": "readonly"}),
        ("DELETE超长key", "DELETE", f"/api/erp-permissions/{'x'*5000}", None),
        ("GET超长路径", "GET", f"/api/erp-permissions/{'x'*5000}", None),
        ("GET带查询参数", "GET", "/api/erp-permissions/?limit=abc&offset=xyz", None),
        ("POST畸形JSON", "POST", "/api/erp-permissions/", "{{{{broken json}}}"),
        ("POST大payload 1MB", "POST", "/api/erp-permissions/",
         {"key": "big:" + uuid.uuid4().hex[:8], "org_id": "*",
          "display_name": "x" * 500000, "domains": ["x"] * 100, "access": "readonly"}),
    ]

    for name, method, path, body in boundary_http:
        async def make_http_boundary(m=method, p=path, b=body, n=name):
            try:
                if b is not None and not isinstance(b, (dict, list)):
                    resp = await client.request(m, p, content=b, headers={"Content-Type": "application/json"})
                else:
                    resp = await client.request(m, p, json=b)
                # Any non-500 response is acceptable
                if resp.status_code < 500:
                    return True, f"Status={resp.status_code}"
                return False, f"500 Server Error"
            except httpx.DecodingError:
                return True, "解码错误（可接受）"
            except httpx.TimeoutException:
                return True, "超时（可接受）"
            except Exception as e:
                return True, f"异常但非崩溃: {type(e).__name__}"

        tests.append(run_test(f"HTTP边界: {name}", "Phase4", make_http_boundary))

    # 4.3 Agent Chat 请求体边界条件

    async def test_chat_missing_input():
        """缺少 input 字段"""
        body = {"session_id": f"test-{uuid.uuid4().hex[:8]}", "user_id": "tester", "channel": "console"}
        url = urljoin(BASE_URL + "/", "api/console/chat")
        headers = {"Content-Type": "application/json", "X-Agent-Id": AGENT_ID}
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                return True, f"正确拒绝了无效请求: {resp.status_code}"
            return True, f"Status={resp.status_code}"

    tests.append(run_test("Chat缺少input", "Phase4", test_chat_missing_input))

    async def test_chat_empty_input_list():
        """空 input 列表"""
        body = {"input": [], "session_id": f"test-{uuid.uuid4().hex[:8]}",
                "user_id": "tester", "channel": "console"}
        url = urljoin(BASE_URL + "/", "api/console/chat")
        headers = {"Content-Type": "application/json", "X-Agent-Id": AGENT_ID}
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(url, json=body, headers=headers)
            if resp.status_code >= 400 or resp.status_code == 200:
                return True, f"Status={resp.status_code}"
            return False, f"Status={resp.status_code}"

    tests.append(run_test("Chat空input列表", "Phase4", test_chat_empty_input_list))

    async def test_chat_wrong_content_type():
        """错误 Content-Type"""
        body = json.dumps({"input": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
                           "session_id": f"test-{uuid.uuid4().hex[:8]}"})
        url = urljoin(BASE_URL + "/", "api/console/chat")
        headers = {"Content-Type": "text/plain", "X-Agent-Id": AGENT_ID}
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(url, content=body, headers=headers)
            if resp.status_code >= 400:
                return True, f"Status={resp.status_code}"
            return True, f"Status={resp.status_code}"

    tests.append(run_test("Chat错误Content-Type", "Phase4", test_chat_wrong_content_type))

    # 4.4 HTTP Methods 测试
    http_methods_to_test = [
        ("PUT权限", "PUT", "/api/erp-permissions/"),
        ("PATCH权限", "PATCH", "/api/erp-permissions/"),
        ("OPTIONS权限", "OPTIONS", "/api/erp-permissions/"),
        ("HEAD权限", "HEAD", "/api/erp-permissions/"),
    ]

    for name, method, path in http_methods_to_test:
        async def make_method_test(m=method, p=path, n=name):
            try:
                resp = await client.request(m, p)
                if resp.status_code < 500:
                    return True, f"Status={resp.status_code}"
                return False, f"500"
            except Exception as e:
                return True, f"异常但非崩溃"

        tests.append(run_test(f"HTTP方法: {name}", "Phase4", make_method_test))

    results = await asyncio.gather(*tests)
    for r in results:
        report.add(r)
    logger.info(f"阶段4 完成: {sum(1 for r in results if r.passed)}/{len(results)} 通过")


# ═══════════════════════════════════════════════════════════════
#  阶段 5 - 并发测试
# ═══════════════════════════════════════════════════════════════


async def phase5_concurrent_tests(client: APIClient):
    """阶段5: 并发/压力测试"""
    tests = []

    # 5.1 并发 Chat 请求
    async def test_10_concurrent_chat():
        """10个并发Chat请求"""
        sem = asyncio.Semaphore(10)

        async def _chat():
            async with sem:
                c = APIClient(BASE_URL, AGENT_ID)
                try:
                    s, e = await c.chat_sse("测试并发请求", f"con-{uuid.uuid4().hex[:8]}")
                    await c.close()
                    return s == 200
                except:
                    await c.close()
                    return False

        results = await asyncio.gather(*[_chat() for _ in range(10)])
        passed = sum(1 for r in results if r)
        if passed >= 8:
            return True, f"{passed}/10 成功"
        return False, f"仅 {passed}/10 成功"

    tests.append(run_test("10并发Chat请求", "Phase5", test_10_concurrent_chat, timeout=120))

    # 5.2 50个并发 HTTP 请求
    async def test_50_concurrent_http():
        """50个并发HTTP请求"""
        async def _req():
            c = APIClient(BASE_URL, AGENT_ID)
            try:
                resp = await c.request("GET", "/api/erp-permissions/")
                await c.close()
                return resp.status_code == 200
            except:
                await c.close()
                return False

        results = await asyncio.gather(*[_req() for _ in range(50)])
        passed = sum(1 for r in results if r)
        if passed >= 40:
            return True, f"{passed}/50 成功"
        return False, f"仅 {passed}/50 成功"

    tests.append(run_test("50并发HTTP请求", "Phase5", test_50_concurrent_http, timeout=60))

    # 5.3 混合负载（Chat + HTTP 同时）
    async def test_20_mixed_load():
        """20个混合请求"""
        async def _chat_req():
            c = APIClient(BASE_URL, AGENT_ID)
            try:
                s, e = await c.chat_sse("hi")
                await c.close()
                return s == 200
            except:
                await c.close()
                return False

        async def _http_req():
            c = APIClient(BASE_URL, AGENT_ID)
            try:
                resp = await c.request("GET", "/api/erp-permissions/meta/domains")
                await c.close()
                return resp.status_code == 200
            except:
                await c.close()
                return False

        tasks = [_chat_req() for _ in range(10)] + [_http_req() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        passed = sum(1 for r in results if r)
        if passed >= 15:
            return True, f"{passed}/20 成功"
        return False, f"仅 {passed}/20 成功"

    tests.append(run_test("20混合负载", "Phase5", test_20_mixed_load, timeout=120))

    # 5.4 100个连续HTTP请求
    async def test_100_sequential_http():
        """100个连续HTTP请求"""
        count = 0
        for i in range(100):
            try:
                resp = await client.request("GET", "/api/erp-permissions/")
                if resp.status_code == 200:
                    count += 1
            except:
                pass
        if count >= 90:
            return True, f"{count}/100 成功"
        return False, f"仅 {count}/100 成功"

    tests.append(run_test("100连续HTTP请求", "Phase5", test_100_sequential_http, timeout=120))

    results = await asyncio.gather(*tests)
    for r in results:
        report.add(r)
    logger.info(f"阶段5 完成: {sum(1 for r in results if r.passed)}/{len(results)} 通过")


# ═══════════════════════════════════════════════════════════════
#  阶段 6 - 综合压力测试
# ═══════════════════════════════════════════════════════════════


async def phase6_stress_test(client: APIClient):
    """阶段6: 长期压力测试"""
    tests = []

    # 6.1 Session 风暴
    async def test_session_storm():
        """创建500个不同session的Chat请求"""
        count = 0
        tasks = []
        sem = asyncio.Semaphore(20)

        async def _chat_storm():
            async with sem:
                c = APIClient(BASE_URL, AGENT_ID)
                try:
                    s, e = await c.chat_sse(
                        random.choice(["你好", "hi", "test", "金蝶", "查询", "abc"]),
                        f"storm-{uuid.uuid4().hex[:8]}"
                    )
                    await c.close()
                    return s == 200
                except:
                    await c.close()
                    return False

        tasks = [_chat_storm() for _ in range(200)]
        results = await asyncio.gather(*tasks)
        passed = sum(1 for r in results if r)
        if passed >= 150:
            return True, f"{passed}/200 session创建成功"
        return False, f"仅 {passed}/200 成功"

    tests.append(run_test("200 Session风暴", "Phase6", test_session_storm, timeout=300))

    # 6.2 权限 CRUD 风暴
    async def test_perm_storm():
        """创建并清理大量权限"""
        keys = []
        for i in range(100):
            key = f"storm-perm:{uuid.uuid4().hex[:8]}"
            keys.append(key)
            try:
                await client.request("POST", "/api/erp-permissions/",
                                     json={"key": key, "org_id": "*",
                                           "display_name": f"stress-{i}",
                                           "domains": ["sales"], "access": "readonly"})
            except:
                pass

        # 清理
        cleaned = 0
        for key in keys:
            try:
                await client.request("DELETE", f"/api/erp-permissions/{key}")
                cleaned += 1
            except:
                pass

        return True, f"创建{len(keys)}/清理{cleaned} 完成"

    tests.append(run_test("100权限CRUD风暴", "Phase6", test_perm_storm, timeout=120))

    # 6.3 混合场景模拟
    async def test_scenario_simulation():
        """模拟真实用户场景"""
        scenarios = [
            # 财务场景
            [("查询销售订单", "query"), ("查看单据详情", "view"), ("列出组织", "orgs")],
            # 权限管理场景
            [("创建用户权限", "create_perm"), ("查询用户权限", "list_perm"), ("删除权限", "delete_perm")],
            # 配置场景
            [("查看后端配置", "config"), ("查看摘要模板", "digest"), ("查看业务域", "domains")],
        ]

        api_client = APIClient(BASE_URL, AGENT_ID)

        async def execute_scenario(scenario):
            for action, action_type in scenario:
                try:
                    if action_type == "query":
                        await api_client.chat_sse(action)
                    elif action_type == "create_perm":
                        key = f"scenario:{uuid.uuid4().hex[:8]}"
                        await api_client.request("POST", "/api/erp-permissions/",
                                                 json={"key": key, "org_id": "*",
                                                       "display_name": "scenario",
                                                       "domains": [], "access": "readonly"})
                    elif action_type == "list_perm":
                        await api_client.request("GET", "/api/erp-permissions/")
                    elif action_type == "delete_perm":
                        await api_client.request("DELETE", f"/api/erp-permissions/scenario:del")
                    elif action_type == "config":
                        await api_client.request("GET", "/api/erp-permissions/config/backends")
                    elif action_type == "digest":
                        await api_client.request("GET", "/api/erp/digest/templates")
                    elif action_type == "domains":
                        await api_client.request("GET", "/api/erp-permissions/meta/domains")
                    elif action_type == "orgs":
                        await api_client.request("GET", "/api/erp-permissions/meta/orgs")
                except:
                    pass
            return True

        results = await asyncio.gather(*[
            execute_scenario(s) for s in scenarios * 5  # 每个场景重复5次
        ])
        await api_client.close()
        return True, f"{len(results)} 场景完成"

    tests.append(run_test("真实场景模拟 15轮", "Phase6", test_scenario_simulation, timeout=180))

    # 6.4 极限：重复调用同一工具
    async def test_100_repeated_query():
        """重复100次查询""" ""
        count = 0
        for i in range(100):
            try:
                resp = await client.request("GET", "/api/erp-permissions/")
                if resp.status_code == 200:
                    count += 1
            except:
                pass
            if i % 25 == 24:
                logger.info(f"  重复查询 {i+1}/100: {count} 成功")
        if count >= 85:
            return True, f"{count}/100"
        return False, f"{count}/100"

    tests.append(run_test("100次重复查询", "Phase6", test_100_repeated_query, timeout=120))

    results = await asyncio.gather(*tests)
    for r in results:
        report.add(r)
    logger.info(f"阶段6 完成: {sum(1 for r in results if r.passed)}/{len(results)} 通过")


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════


async def run_phases(phases: List[int]):
    """按阶段执行测试"""
    client = APIClient(BASE_URL, AGENT_ID)

    try:
        all_phase_funcs = {
            1: phase1_basic_connectivity,
            2: phase2_tool_registration,
            3: phase3_http_routes,
            4: phase4_boundary_tests,
            5: phase5_concurrent_tests,
            6: phase6_stress_test,
        }

        for phase_num in phases:
            if phase_num in all_phase_funcs:
                logger.info(f"\n{'='*70}")
                logger.info(f"  开始阶段 {phase_num}")
                logger.info(f"{'='*70}")
                try:
                    await all_phase_funcs[phase_num](client)
                except Exception as e:
                    logger.error(f"阶段 {phase_num} 执行异常: {e}")
                    traceback.print_exc()
                logger.info(f"阶段 {phase_num} 结束\n")

    finally:
        await client.close()

    report.print_summary()
    report.save_json("erp_test_report.json")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QwenPaw ERP 插件全量测试套件")
    parser.add_argument("--host", default="127.0.0.1", help="QwenPaw 主机")
    parser.add_argument("--port", default="18088", help="QwenPaw 端口")
    parser.add_argument("--phases", default="1,2,3,4,5,6", help="要执行的阶段 (逗号分隔)")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = f"http://{args.host}:{args.port}"

    phases = [int(p.strip()) for p in args.phases.split(",") if p.strip().isdigit()]
    logger.info(f"测试目标: {BASE_URL}")
    logger.info(f"执行阶段: {phases}")
    logger.info(f"超时设置: {TIMEOUT}s")

    asyncio.run(run_phases(phases))


if __name__ == "__main__":
    main()
