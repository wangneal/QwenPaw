# -*- coding: utf-8 -*-
"""金蝶云星空旗舰版 SDK 封装（V2 RESTful API）

认证流程：getAppToken.do -> login.do -> access_token（Bearer token）
API 格式：POST /v2/{app_number}/{form_id}/{operation}

URL 示例：
  /v2/sm/sm_delivernotice/batchQuery
  /v2/basedata/bd_supplier/batchSave
  /v2/im/im_otherinbill/batchDelete

form_id -> app_number 映射来自 v2_form_mapping.json（从API文档提取）。
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import httpx

# 复用经典版的日志和缓存组件
from backends.kingdee.sdk import (
    QueryCache, _truncate, _DailyFileHandler, _LOG_DIR,
    RequestIdFilter,
)

_logger = logging.getLogger("kingdee_flagship.sdk")
logger = logging.getLogger(__name__)

# 旗舰版日志（独立文件）
if not _logger.handlers:
    _req_filter = RequestIdFilter()
    _handler = _DailyFileHandler(_LOG_DIR, prefix="kingdee_flagship")
    _handler.addFilter(_req_filter)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | [%(request_id)s] | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.DEBUG)

# ── V2 URL 解析 ──────────────────────────────────────────────

def _load_v2_mapping() -> tuple[dict, dict]:
    """从 v2_form_mapping.json 加载映射。

    Returns:
        (form_op_url, form_fallback_app)
        form_op_url: form_id -> operation -> {"url": url_path, "app": app}
        form_fallback_app: form_id -> app (fallback)
    """
    mapping_path = os.path.join(os.path.dirname(__file__), "v2_form_mapping.json")
    if not os.path.exists(mapping_path):
        _logger.warning("v2_form_mapping.json 不存在")
        return {}, {}
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("form_op_url", {}),
            data.get("form_fallback_app", {}),
        )
    except Exception as e:
        _logger.warning("加载 v2_form_mapping.json 失败: %s", e)
        return {}, {}

# 模块级缓存
_V2_FORM_OP_URL: dict = {}
_V2_FALLBACK_APP: dict = {}

def _ensure_v2_map():
    global _V2_FORM_OP_URL, _V2_FALLBACK_APP
    if not _V2_FORM_OP_URL:
        _V2_FORM_OP_URL, _V2_FALLBACK_APP = _load_v2_mapping()

def resolve_v2_url(form_id: str, operation: str) -> str:
    """根据 form_id 和 operation 解析完整的 V2 API URL 路径。

    返回格式：v2/{app}/{form_id}/{operation} 或 API 文档中定义的自定义路径。

    查找顺序：
    1. 精确匹配 form_id + operation
    2. 从 fallback app + form_id + operation 构建
    3. 从 form_id 前缀推断 app
    """
    _ensure_v2_map()

    # 1. 精确匹配
    form_ops = _V2_FORM_OP_URL.get(form_id, {})
    if operation in form_ops:
        url = form_ops[operation].get("url", "")
        if url:
            return url

    # 2. 从 fallback app 构建
    app = _V2_FALLBACK_APP.get(form_id, "")
    if app:
        _logger.warning("[V2Map] 使用fallback URL: form=%s op=%s app=%s", form_id, operation, app)
        return f"v2/{app}/{form_id}/{operation}"

    # 3. 从 form_id 前缀推断
    prefix_map: dict[str, str] = {}
    for fid, app in _V2_FALLBACK_APP.items():
        if "_" in fid:
            prefix = fid.split("_")[0]
            if prefix not in prefix_map:
                prefix_map[prefix] = app
    sorted_prefixes = sorted(prefix_map.keys(), key=len, reverse=True)
    for prefix in sorted_prefixes:
        if form_id.lower().startswith(prefix.lower()):
            _logger.warning("[V2Map] 使用前缀推断URL: form=%s op=%s prefix=%s app=%s",
                            form_id, operation, prefix, prefix_map[prefix])
            return f"v2/{prefix_map[prefix]}/{form_id}/{operation}"

    # 4. 硬编码兜底
    FALLBACK_PREFIX_MAP = {
        "bd_": "basedata", "sal_": "sm", "pur_": "pm",
        "ar_": "ar", "ap_": "ap", "gl_": "gl", "fa_": "fa",
        "hs_": "cal", "stk_": "im", "po_": "pm", "pr_": "pm",
    }
    for prefix, app in FALLBACK_PREFIX_MAP.items():
        if form_id.lower().startswith(prefix):
            _logger.warning("[V2Map] 使用硬编码兜底: form=%s op=%s prefix=%s app=%s",
                            form_id, operation, prefix, app)
            return f"v2/{app}/{form_id}/{operation}"

    _logger.error("[V2Map] 无法解析URL: form=%s op=%s", form_id, operation)


# ══════════════════════════════════════════════════════════════
# 客户端
# ══════════════════════════════════════════════════════════════


class KingdeeFlagshipClient:
    """金蝶云星空旗舰版 API 客户端（V2 RESTful API）

    认证流程：
    1. POST /api/getAppToken.do -> 获取 apptoken
    2. POST /api/login.do -> 获取 access_token
    3. 后续请求使用 Authorization: Bearer {access_token}

    V2 API 格式：
    POST /v2/{app_number}/{form_id}/{operation}
    """

    def __init__(
        self,
        server_url: str,
        app_id: str,
        app_secret: str,
        tenantid: str,
        account_id: str,
        user_name: str,
        kd_language: str = "zh_CN",
        cache_ttl: int = 300,
    ):
        import httpx
        self.server_url = server_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenantid = tenantid
        self.account_id = account_id
        self.user_name = user_name
        self.kd_language = kd_language
        self._cache = QueryCache(ttl=cache_ttl)
        self._init_lock = asyncio.Lock()
        self._access_token: Optional[str] = None
        self._token_expires: Optional[float] = None
        # 复用 httpx 客户端（带连接池）
        self._http: Optional[httpx.AsyncClient] = None

    # ── 认证 ──────────────────────────────────────────────────

    async def _authenticate(self):
        """旗舰版认证：getAppToken.do + login.do"""
        base_url = self.server_url.rstrip("/")

        # Step 1: 获取 appToken
        app_token_url = f"{base_url}/api/getAppToken.do"
        app_token_body = {
            "appId": self.app_id,
            "appSecret": self.app_secret,
            "tenantid": self.tenantid,
            "accountId": self.account_id,
        }
        _logger.info("[FlagshipAuth] 获取appToken url=%s", app_token_url)
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30)
        resp = await self._http.post(app_token_url, json=app_token_body)
        resp.raise_for_status()
        app_token_data = resp.json()

        # 兼容多种响应格式
        _code = app_token_data.get("code")
        _errcode = app_token_data.get("errcode")
        if _code not in (0, None) and _errcode not in (0, None):
            data = app_token_data.get("data", {})
            if not data or (not data.get("appToken") and not data.get("apptoken")):
                raise RuntimeError(f"获取appToken失败: {_truncate(app_token_data)}")

        apptoken = (
            app_token_data.get("data", {}).get("appToken")
            or app_token_data.get("data", {}).get("apptoken")
            or app_token_data.get("appToken")
            or app_token_data.get("apptoken")
        )
        if not apptoken:
            raise RuntimeError(f"appToken为空，响应: {_truncate(app_token_data)}")

        # Step 2: 登录获取 access_token
        login_url = f"{base_url}/api/login.do"
        login_body = {
            "user": self.user_name,
            "usertype": "Mobile",
            "apptoken": apptoken,
            "tenantid": self.tenantid,
            "accountId": self.account_id,
            "language": self.kd_language,
        }
        _logger.info("[FlagshipAuth] 登录 url=%s user=%s", login_url, self.user_name)
        resp = await self._http.post(login_url, json=login_body)
        resp.raise_for_status()
        login_data = resp.json()

        _lcode = login_data.get("code")
        _lerrcode = login_data.get("errcode")
        if _lcode not in (0, None) and _lerrcode not in (0, None):
            raise RuntimeError(f"旗舰版登录失败: {_truncate(login_data)}")

        access_token = (
            login_data.get("data", {}).get("access_token")
            or login_data.get("access_token")
        )
        if not access_token:
            raise RuntimeError(f"access_token为空，响应: {_truncate(login_data)}")

        self._access_token = access_token
        # 2小时过期，提前5分钟刷新
        self._token_expires = time.time() + 7200 - 300
        _logger.info("[FlagshipAuth] 认证成功，access_token已获取")
        logger.info("Flagship auth succeeded for user=%s", self.user_name)

    async def _ensure(self):
        """确保已认证（token过期自动续期）"""
        if self._access_token and self._token_expires:
            if time.time() < self._token_expires:
                return
            _logger.info("[FlagshipAuth] access_token即将过期，重新认证")

        async with self._init_lock:
            if self._access_token and self._token_expires and time.time() < self._token_expires:
                return
            await self._authenticate()

    # ── 健康检查 ──────────────────────────────────────────────

    async def health_check(self) -> bool:
        """健康检查：尝试认证"""
        try:
            await self._ensure()
            return self._access_token is not None
        except Exception as e:
            _logger.error("[FlagshipHealthCheck] 失败: %s", e, exc_info=True)
            return False

    # ── V2 RESTful API 请求 ──────────────────────────────────

    async def request_v2(
        self,
        form_id: str,
        operation: str,
        body: Optional[dict] = None,
        use_cache: bool = False,
    ) -> Any:
        """通用 V2 RESTful API 请求。

        Args:
            form_id: 表单ID（如 sm_delivernotice, bd_supplier）
            operation: 操作码（如 batchQuery, batchSave, batchDelete 等）
            body: 请求体（表单特定的JSON数据）
            use_cache: 是否使用缓存（仅对查询类操作有效）

        Returns:
            API 响应数据（可能是 dict 或 list）
        """
        await self._ensure()

        # 解析完整 V2 URL 路径
        url_path = resolve_v2_url(form_id, operation)
        if not url_path:
            raise ValueError(
                f"无法确定表单 '{form_id}' 的操作 '{operation}' 的 API 路径。"
                f"请确认 form_id 和 operation 是否正确。"
            )

        base_url = self.server_url.rstrip("/")
        url = f"{base_url}/{url_path}"

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        _logger.info("[FlagshipV2] POST %s body=%s", url_path, _truncate(body or {}, 500))

        # 缓存读（仅查询类操作）
        if use_cache and any(op in operation.lower() for op in ("query", "get", "list")):
            ck = QueryCache.make_key(form_id, operation, str(body))
            cached = await self._cache.get(ck)
            if cached is not None:
                _logger.info("[FlagshipV2] 缓存命中 form=%s op=%s", form_id, operation)
                return cached

        t0 = time.time()

        # 请求 + 401 自动重试
        for attempt in range(2):
            if self._http is None:
                self._http = httpx.AsyncClient(timeout=120)
            resp = await self._http.post(url, json=body or {}, headers=headers)

            if resp.status_code == 401 and attempt == 0:
                _logger.info("[FlagshipV2] 401 token过期，重新认证后重试")
                self._access_token = None
                await self._ensure()
                headers["Authorization"] = f"Bearer {self._access_token}"
                continue

            resp.raise_for_status()
            result = resp.json()
            break
        elapsed = (time.time() - t0) * 1000

        _logger.info("[FlagshipV2] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))

        # 缓存写（仅查询类操作）
        if use_cache and any(op in operation.lower() for op in ("query", "get", "list")):
            ck = QueryCache.make_key(form_id, operation, str(body))
            await self._cache.set(ck, result, form_id=form_id)

        return result

    # ── 便利方法 ──────────────────────────────────────────────

    async def get_org_names(self, org_ids: list) -> dict:
        """查询组织名称映射"""
        if not org_ids:
            return {}
        try:
            # V2 API: bos_org query 通过 number 过滤
            body = {
                "number": [str(oid) for oid in org_ids if oid],
            }
            result = await self.request_v2("bos_org", "getList", body)
            # 兼容 list 和 dict 格式
            rows = result if isinstance(result, list) else result.get("data", []) if isinstance(result, dict) else []
            # bos_org query 返回 [{id, number, name, ...}, ...]
            if rows and isinstance(rows[0], dict):
                return {row.get("number", ""): row.get("name", "") for row in rows}
            elif rows and isinstance(rows[0], list):
                return {row[0]: row[1] for row in rows if len(row) >= 2}
            return {}
        except Exception as e:
            _logger.warning("[OrgNames] 查询失败: %s", e)
            return {}

    async def clear_cache(self, form_id: str = ""):
        """清除缓存"""
        if form_id:
            await self._cache.clear_by_form_id(form_id)
        else:
            await self._cache.clear()

    async def get_cache_stats(self) -> dict:
        """获取缓存统计"""
        return await self._cache.stats()
