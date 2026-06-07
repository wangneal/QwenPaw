# -*- coding: utf-8 -*-
"""金蝶云星空 WebAPI SDK 封装

所有金蝶 WebAPI 调用的唯一出口，提供：
- KingdeeClient: 高级金蝶 API 客户端
- QueryCache: 查询结果缓存（线程安全）
- 日志: 请求/响应/耗时全部记录到文件，按日期分割
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

# ── 日志配置 ──────────────────────────────────────────────────
# 独立日志文件，按日期分割，保留 30 天
# 日志路径: ~/.qwenpaw/plugin_data/erp/logs/kingdee_YYYY-MM-DD.log
_LOG_DIR = os.path.join(
    os.path.expanduser("~"), ".qwenpaw", "plugin_data", "erp", "logs"
)
os.makedirs(_LOG_DIR, exist_ok=True)

_logger = logging.getLogger("kingdee.sdk")

# ── Request ID 过滤器 ──────────────────────────────────────────────
# 从 erp_backend 框架层的 ContextVar 读取 request_id，
# 自动注入到每条日志记录中，格式: [req:a1b2c3d4e5f6]
try:
    from erp_backend import RequestIdFilter
except ImportError:
    # 降级：定义空 Filter 以避免导入失败
    class RequestIdFilter(logging.Filter):
        def filter(self, record):
            record.request_id = "-"
            return True


class _DailyFileHandler(logging.FileHandler):
    """每天一个独立 .log 文件，文件名含日期（如 kingdee_2026-05-31.log）"""

    def __init__(self, log_dir: str, prefix: str = "kingdee", encoding: str = "utf-8"):
        self._log_dir = log_dir
        self._prefix = prefix
        self._current_date = ""
        # 先计算今天的文件名再打开
        self._current_date = time.strftime("%Y-%m-%d")
        filename = os.path.join(log_dir, f"{prefix}_{self._current_date}.log")
        super().__init__(filename, encoding=encoding)

    def emit(self, record):
        try:
            today = time.strftime("%Y-%m-%d")
            if today != self._current_date:
                self._current_date = today
                self.close()
                self.baseFilename = os.path.join(self._log_dir, f"{self._prefix}_{today}.log")
                self.stream = open(self.baseFilename, self.encoding)
            super().emit(record)
        except (OSError, ValueError):
            # 文件打开/写入失败时使用 handleError 避免日志系统崩溃
            self.handleError(record)


if not _logger.handlers:
    _req_filter = RequestIdFilter()

    # 全量日志：kingdee_2026-05-31.log
    _handler = _DailyFileHandler(_LOG_DIR, prefix="kingdee")
    _handler.addFilter(_req_filter)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | [%(request_id)s] | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _logger.addHandler(_handler)

    # 错误日志：kingdee_error_2026-05-31.log（仅 ERROR 及以上）
    _error_handler = _DailyFileHandler(_LOG_DIR, prefix="kingdee_error")
    _error_handler.addFilter(_req_filter)
    _error_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | [%(request_id)s] | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _error_handler.setLevel(logging.ERROR)
    _logger.addHandler(_error_handler)

    _logger.setLevel(logging.DEBUG)

# 同时保留 __name__ logger 用于 QwenPaw 主日志
logger = logging.getLogger(__name__)

try:
    from k3cloud_webapi_sdk.main import K3CloudApiSdk
    HAS_OFFICIAL_SDK = True
except ImportError:
    HAS_OFFICIAL_SDK = False
    logger.warning(
        "k3cloud_webapi_sdk 未安装。"
        "安装方式: pip install ./backends/kingdee/kingdee.cdp.webapi.sdk-8.2.0-py3-none-any.whl"
    )


def _truncate(obj: Any, max_len: int = 2000) -> str:
    """将对象 JSON 序列化后截断，避免日志过长"""
    try:
        text = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(obj)
    if len(text) > max_len:
        return text[:max_len] + f"... (truncated, total={len(text)})"
    return text


# ── 查询缓存 ──────────────────────────────────────────────────
class QueryCache:
    """查询结果缓存（线程安全，基于 asyncio.Lock）"""

    def __init__(self, ttl: int = 300, max_size: int = 200):
        self._cache: dict[str, tuple[float, Any, str]] = {}  # 键 -> (时间戳, 值, 表单ID)
        self._lock = asyncio.Lock()
        self._ttl = ttl
        self._max_size = max_size

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                _logger.debug("[Cache] MISS key=%s", key)
                return None
            ts, value, _ = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                _logger.debug("[Cache] EXPIRED key=%s", key)
                return None
            _logger.debug("[Cache] HIT key=%s", key)
            return value

    async def set(self, key: str, value: Any, form_id: str = "") -> None:
        async with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
                _logger.debug("[Cache] EVICT key=%s (max_size=%d)", oldest_key, self._max_size)
            self._cache[key] = (time.time(), value, form_id)
            _logger.debug("[Cache] SET key=%s", key)

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                _logger.debug("[Cache] INVALIDATE key=%s", key)

    async def clear_by_form_id(self, form_id: str) -> int:
        """按 form_id 清除缓存条目（写入后清除关联查询缓存）。

        Returns:
            清除的条目数
        """
        async with self._lock:
            keys_to_remove = [k for k, (_, _, fid) in self._cache.items() if fid == form_id]
            for k in keys_to_remove:
                del self._cache[k]
            if keys_to_remove:
                _logger.debug("[Cache] CLEAR_BY_FORM_ID form_id=%s count=%d", form_id, len(keys_to_remove))
            return len(keys_to_remove)

    async def clear(self) -> None:
        """清空全部缓存。"""
        async with self._lock:
            self._cache.clear()
            _logger.debug("[Cache] CLEAR ALL")

    @staticmethod
    def make_key(form_id: str, field_keys: str, filter_str: str, **kwargs) -> str:
        raw = f"{form_id}|{field_keys}|{filter_str}|{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()


# ── 金蝶客户端 ────────────────────────────────────────────────
class KingdeeClient:
    """金蝶云星空 WebAPI 高级客户端

    所有 API 方法自动记录请求、响应、耗时到日志文件。
    """

    def __init__(
        self,
        server_url: str,
        acct_id: str,
        user_name: str,
        app_id: str,
        app_secret: str,
        lcid: int = 2052,
        org_num: int = 0,
        cache_ttl: int = 300,
    ):
        self.server_url = server_url.rstrip("/")
        self.acct_id = acct_id
        self.user_name = user_name
        self.app_id = app_id
        self.app_secret = app_secret
        self.lcid = lcid
        self.org_num = org_num
        self._cache = QueryCache(ttl=cache_ttl)
        self._sdk = None
        self._init_lock = asyncio.Lock()

    async def _ensure(self):
        """初始化 SDK（双重检查锁防竞态）"""
        if self._sdk:
            return
        async with self._init_lock:
            if self._sdk:
                return
            if not HAS_OFFICIAL_SDK:
                raise RuntimeError("k3cloud_webapi_sdk not installed")
            self._sdk = K3CloudApiSdk(self.server_url)
            self._sdk.InitConfig(
                self.acct_id, self.user_name, self.app_id,
                self.app_secret, self.server_url, self.lcid, self.org_num,
            )
            _logger.info("[SDK] 初始化成功 server=%s acct=%s", self.server_url, self.acct_id)
            logger.info("Kingdee SDK initialized: %s", self.server_url)

    async def health_check(self) -> bool:
        try:
            await self._ensure()
            data = {"FormId": "BD_Material", "FieldKeys": "FNumber", "TopRowCount": 1}
            _logger.info("[HealthCheck] 请求 data=%s", _truncate(data))
            t0 = time.time()
            r = self._sdk.ExecuteBillQuery(data)
            elapsed = (time.time() - t0) * 1000
            _logger.info("[HealthCheck] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(r, 200))
            return r is not None
        except Exception as e:
            _logger.error("[HealthCheck] 失败: %s", e, exc_info=True)
            return False

    # ── 查询 ──────────────────────────────────────────────────

    async def execute_bill_query(
        self, form_id, field_keys, filter_string="",
        order_string="", top_row_count=100, start_row=0,
        limit=2000, use_cache=True,
    ) -> list:
        ck = QueryCache.make_key(form_id, field_keys, filter_string,
                                  order=order_string, top=top_row_count)
        if use_cache:
            cached = await self._cache.get(ck)
            if cached is not None:
                _logger.info("[Query] 缓存命中 form_id=%s fields=%s", form_id, field_keys[:60])
                return cached
        await self._ensure()
        data = {
            "FormId": form_id, "FieldKeys": field_keys,
            "FilterString": filter_string, "OrderString": order_string,
            "TopRowCount": top_row_count, "StartRow": start_row,
            "Limit": limit,
        }
        _logger.info("[Query] 请求 form_id=%s fields=%s filter=%s",
                     form_id, field_keys[:80], _truncate(filter_string, 200))
        t0 = time.time()
        r = self._sdk.ExecuteBillQuery(data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Query] 响应 elapsed=%.0fms rows=%d", elapsed, len(result) if isinstance(result, list) else -1)
        _logger.debug("[Query] 响应详情 %s", _truncate(result))
        if use_cache:
            await self._cache.set(ck, result, form_id=form_id)
        return result

    async def bill_query(
        self, form_id, field_keys, filter_string="",
        order_string="", top_row_count=100, start_row=0, limit=2000,
    ):
        await self._ensure()
        data = {
            "FormId": form_id, "FieldKeys": field_keys,
            "FilterString": filter_string, "OrderString": order_string,
            "TopRowCount": top_row_count, "StartRow": start_row,
            "Limit": limit,
        }
        _logger.info("[BillQuery] 请求 form_id=%s fields=%s", form_id, field_keys[:80])
        t0 = time.time()
        r = self._sdk.BillQuery(data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[BillQuery] 响应 elapsed=%.0fms", elapsed)
        _logger.debug("[BillQuery] 响应详情 %s", _truncate(result))
        return result

    async def view_bill(self, form_id, number="", bill_id="") -> dict:
        await self._ensure()
        data = {"CreateOrgId": 0, "Number": number, "Id": bill_id, "IsSortBySeq": "false"}
        _logger.info("[View] 请求 form_id=%s number=%s bill_id=%s", form_id, number, bill_id)
        t0 = time.time()
        r = self._sdk.View(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[View] 响应 elapsed=%.0fms", elapsed)
        _logger.debug("[View] 响应详情 %s", _truncate(result))
        return result

    async def get_report_data(self, form_id, parameters) -> Any:
        """标准报表查询（GetSysReportData）。"""
        await self._ensure()
        data = {"parameters": [parameters]}
        _logger.info("[Report] 请求 form_id=%s params=%s", form_id, _truncate(parameters))
        t0 = time.time()
        r = self._sdk.GetSysReportData(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Report] 响应 elapsed=%.0fms", elapsed)
        _logger.debug("[Report] 响应详情 %s", _truncate(result))
        return result

    async def get_report_paged(
        self, form_id: str, scheme_id: str,
        quickly_conditions: list = None,
    ) -> Any:
        """分页账表查询（GetSysReportData + FSCHEMEID）。"""
        await self._ensure()
        param_obj = {"FORMID": form_id, "FSCHEMEID": scheme_id}
        if quickly_conditions:
            param_obj["QuicklyCondition"] = quickly_conditions
        data = {"parameters": [json.dumps(param_obj)]}
        _logger.info("[ReportPaged] 请求 form_id=%s scheme_id=%s conditions=%s",
                     form_id, scheme_id, _truncate(quickly_conditions))
        t0 = time.time()
        r = self._sdk.GetSysReportData(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[ReportPaged] 响应 elapsed=%.0fms", elapsed)
        _logger.debug("[ReportPaged] 响应详情 %s", _truncate(result))
        return result

    # ── 合并报表（KDS）──────────────────────────────────────

    async def get_kds_report_data(self, parameters: dict) -> Any:
        """合并报表查询（KDSReportAPIStub.GetReportData）。

        用于查询合并报表、汇总报表、工作底稿、抵消表等。

        Args:
            parameters: 报表参数，包含：
                - ReportType: 报表类型（1=个别, 2=穿透, 14=汇总, 15=合并, 16=工作底稿等）
                - ReportNumber: 报表编码
                - AcctSystemNumber: 核算体系编号
                - AcctPolicyNumber: 会计政策编号
                - OrgNumber: 组织编号（部分报表需要）
                - CurrencyNumber: 币别编号
                - CurrUnitNumber: 币别单位编号
                - CycleType: 周期类型（1=会计期间, 4=月报, 5=季报, 7=年报等）
                - Year: 年份
                - Period: 期间
                - DataType: 数据格式（Json/Excel/Itemdata）
                - ScopeTypeNumber: 合并方案编号（部分报表需要）
                - ScopeNumber: 合并范围编号（部分报表需要）
        """
        await self._ensure()
        data = {"parameter": parameters}
        _logger.info("[KDSReport] 请求 params=%s", _truncate(parameters))
        t0 = time.time()
        # 使用合并报表专用 API
        r = self._sdk.ExecuteByString(
            "Kingdee.BOS.KDS.ServiceFacade.ServicesStub.KDSReportAPIStub.GetReportData,Kingdee.BOS.KDS.ServiceFacade.ServicesStub.common.kdsvc",
            json.dumps(data)
        )
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[KDSReport] 响应 elapsed=%.0fms", elapsed)
        _logger.debug("[KDSReport] 响应详情 %s", _truncate(result))
        return result

    # ── 写入 ──────────────────────────────────────────────────

    async def save_bill(self, form_id, model, **kw) -> dict:
        await self._ensure()
        data = {
            "NeedUpDateFields": [], "NeedReturnFields": [],
            "IsDeleteEntry": "True", "IsVerifyBaseDataField": "False",
            "IsEntryBatchFill": "True", "ValidateFlag": "True",
            "NumberSearch": "True", "IsAutoAdjustField": "False",
            "InterationFlags": "", "IgnoreInterationFlag": "",
            "IsControlPrecision": "False", "Model": model,
        }
        data.update(kw)
        _logger.info("[Save] 请求 form_id=%s model=%s", form_id, _truncate(model))
        t0 = time.time()
        r = self._sdk.Save(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Save] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[Save] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def delete_bill(self, form_id, numbers=None, ids="") -> dict:
        await self._ensure()
        data = {"CreateOrgId": 0, "Numbers": numbers or [], "Ids": ids}
        target = ",".join(numbers) if numbers else ids
        _logger.info("[Delete] 请求 form_id=%s target=%s", form_id, target)
        t0 = time.time()
        r = self._sdk.Delete(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Delete] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[Delete] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def submit_bill(self, form_id, numbers=None, ids="") -> dict:
        await self._ensure()
        data = {"CreateOrgId": 0, "Numbers": numbers or [], "Ids": ids}
        target = ",".join(numbers) if numbers else ids
        _logger.info("[Submit] 请求 form_id=%s target=%s", form_id, target)
        t0 = time.time()
        r = self._sdk.Submit(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Submit] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[Submit] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def audit_bill(self, form_id, numbers=None, ids="") -> dict:
        await self._ensure()
        data = {"CreateOrgId": 0, "Numbers": numbers or [], "Ids": ids}
        target = ",".join(numbers) if numbers else ids
        _logger.info("[Audit] 请求 form_id=%s target=%s", form_id, target)
        t0 = time.time()
        r = self._sdk.Audit(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Audit] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[Audit] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def unaudit_bill(self, form_id, numbers=None, ids="") -> dict:
        await self._ensure()
        data = {"CreateOrgId": 0, "Numbers": numbers or [], "Ids": ids}
        target = ",".join(numbers) if numbers else ids
        _logger.info("[UnAudit] 请求 form_id=%s target=%s", form_id, target)
        t0 = time.time()
        r = self._sdk.UnAudit(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[UnAudit] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[UnAudit] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def push_bill(self, form_id, push_data) -> dict:
        await self._ensure()
        _logger.info("[Push] 请求 form_id=%s data=%s", form_id, _truncate(push_data))
        t0 = time.time()
        r = self._sdk.Push(form_id, push_data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Push] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[Push] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def execute_operation(self, form_id, op_number, op_data) -> dict:
        await self._ensure()
        _logger.info("[ExecuteOp] 请求 form_id=%s op=%s data=%s", form_id, op_number, _truncate(op_data))
        t0 = time.time()
        r = self._sdk.ExcuteOperation(form_id, op_number, op_data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[ExecuteOp] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[ExecuteOp] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def allocate_base_data(self, form_id, pk_ids, target_org_ids) -> dict:
        """基础资料分配（Allocate）。

        Args:
            form_id: 基础资料表单ID，如 BD_Customer
            pk_ids: 被分配基础资料内码集合，逗号分隔字符串
            target_org_ids: 目标组织内码集合，逗号分隔字符串
        """
        await self._ensure()
        data = {"PkIds": str(pk_ids), "TOrgIds": str(target_org_ids)}
        _logger.info("[Allocate] 请求 form_id=%s data=%s", form_id, _truncate(data))
        t0 = time.time()
        if not hasattr(self._sdk, "Allocate"):
            raise RuntimeError("当前金蝶 SDK 不支持 Allocate 接口")
        r = self._sdk.Allocate(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[Allocate] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[Allocate] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def cancel_allocate_base_data(self, form_id, pk_ids, target_org_ids) -> dict:
        """基础资料取消分配（CancelAllocate）。"""
        await self._ensure()
        data = {"PkIds": str(pk_ids), "TOrgIds": str(target_org_ids)}
        _logger.info("[CancelAllocate] 请求 form_id=%s data=%s", form_id, _truncate(data))
        t0 = time.time()
        if not hasattr(self._sdk, "CancelAllocate"):
            raise RuntimeError("当前金蝶 SDK 不支持 CancelAllocate 接口")
        r = self._sdk.CancelAllocate(form_id, data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[CancelAllocate] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[CancelAllocate] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def group_save_base_data(self, form_id, group_data) -> dict:
        """基础资料分组保存（GroupSave）。"""
        await self._ensure()
        _logger.info("[GroupSave] 请求 form_id=%s data=%s", form_id, _truncate(group_data))
        t0 = time.time()
        if not hasattr(self._sdk, "GroupSave"):
            raise RuntimeError("当前金蝶 SDK 不支持 GroupSave 接口")
        r = self._sdk.GroupSave(form_id, group_data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[GroupSave] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[GroupSave] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def query_group_info(self, form_id, group_field_key="", group_pk_ids="", ids="") -> dict:
        """基础资料分组信息查询（QueryGroupInfo）。"""
        await self._ensure()
        data = {
            "FormId": form_id,
            "GroupFieldKey": group_field_key or "",
            "GroupPkIds": group_pk_ids or "",
            "Ids": ids or "",
        }
        _logger.info("[QueryGroupInfo] 请求 form_id=%s data=%s", form_id, _truncate(data))
        t0 = time.time()
        if not hasattr(self._sdk, "QueryGroupInfo"):
            raise RuntimeError("当前金蝶 SDK 不支持 QueryGroupInfo 接口")
        r = self._sdk.QueryGroupInfo(data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[QueryGroupInfo] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[QueryGroupInfo] 响应详情 %s", _truncate(result))
        return result

    async def group_delete_base_data(self, form_id, group_field_key="", group_pk_ids="") -> dict:
        """基础资料分组删除（GroupDelete）。"""
        await self._ensure()
        data = {
            "FormId": form_id,
            "GroupFieldKey": group_field_key or "",
            "GroupPkIds": group_pk_ids or "",
        }
        _logger.info("[GroupDelete] 请求 form_id=%s data=%s", form_id, _truncate(data))
        t0 = time.time()
        if not hasattr(self._sdk, "GroupDelete"):
            raise RuntimeError("当前金蝶 SDK 不支持 GroupDelete 接口")
        r = self._sdk.GroupDelete(data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[GroupDelete] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[GroupDelete] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def workflow_audit(self, form_id, numbers, user_id, approval_type=1) -> dict:
        """工作流审批。

        Args:
            form_id: 表单标识（如 PUR_PurchaseOrder）
            numbers: 单据编号列表（如 ["CGDD000695"]）
            user_id: 审批人内码（T_SEC_USER.FUSERID）
            approval_type: 审批类型（1=通过, 2=驳回, 3=终止）
        """
        await self._ensure()
        data = {
            "FormId": form_id,
            "Numbers": numbers,
            "UserId": user_id,
            "ApprovalType": approval_type,
        }
        type_label = {1: "通过", 2: "驳回", 3: "终止"}.get(approval_type, str(approval_type))
        _logger.info("[WorkflowAudit] 请求 form_id=%s numbers=%s type=%s user=%s",
                     form_id, numbers, type_label, user_id)
        t0 = time.time()
        r = self._sdk.WorkflowAudit(json.dumps(data))
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[WorkflowAudit] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        _logger.debug("[WorkflowAudit] 响应详情 %s", _truncate(result))
        await self._cache.clear_by_form_id(form_id)
        return result

    async def switch_org(self, org_number) -> dict:
        await self._ensure()
        data = {"Model": {"FSALEORGID": {"FNumber": org_number}}}
        _logger.info("[SwitchOrg] 请求 org=%s", org_number)
        t0 = time.time()
        r = self._sdk.SwitchOrg(data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[SwitchOrg] 响应 elapsed=%.0fms result=%s", elapsed, _truncate(result, 500))
        return result

    async def query_business_info(self, form_id="") -> Any:
        await self._ensure()
        data = {"FormId": form_id} if form_id else {}
        _logger.info("[QueryBizInfo] 请求 form_id=%s", form_id or "(all)")
        t0 = time.time()
        r = self._sdk.QueryBusinessInfo(data)
        elapsed = (time.time() - t0) * 1000
        result = json.loads(r) if isinstance(r, str) else r
        _logger.info("[QueryBizInfo] 响应 elapsed=%.0fms", elapsed)
        _logger.debug("[QueryBizInfo] 响应详情 %s", _truncate(result))
        return result

    async def get_org_names(self, org_ids: list) -> dict:
        """查询组织名称映射。"""
        if not org_ids:
            return {}
        try:
            await self._ensure()
            # 校验 org_ids 白名单：只允许数字和字母，防止注入
            import re as _re_mod
            safe_ids = []
            for oid in org_ids:
                if not oid or not _re_mod.fullmatch(r'^[A-Za-z0-9_.\-]+$', str(oid)):
                    logger.warning("get_org_names: org_id 包含非法字符，已跳过: %r", oid)
                    continue
                safe_ids.append(f"'{oid}'")
            if not safe_ids:
                return {}
            filter_str = ",".join(safe_ids)
            data = {
                "FormId": "BD_Org",
                "FieldKeys": "FNumber,FName",
                "FilterString": f"FNumber IN ({filter_str})",
                "TopRowCount": len(org_ids),
            }
            _logger.info("[OrgNames] 请求 org_ids=%s", org_ids)
            t0 = time.time()
            r = self._sdk.ExecuteBillQuery(data)
            elapsed = (time.time() - t0) * 1000
            result = json.loads(r) if isinstance(r, str) else r
            names = {row[0]: row[1] for row in result if len(row) >= 2}
            _logger.info("[OrgNames] 响应 elapsed=%.0fms found=%d", elapsed, len(names))
            return names
        except Exception as e:
            _logger.warning("[OrgNames] 查询失败，降级显示ID: %s", e)
            logger.warning("Failed to query org names: %s", e)
            return {}
