# -*- coding: utf-8 -*-
"""ERP Backend Protocol and Registry for multi-system support.

This module defines the abstract interface that all ERP backends must implement,
enabling a unified plugin architecture that supports Kingdee, SAP, Oracle, etc.

Architecture:
- ERPBackend: Protocol (runtime_checkable) defining required backend interface
- BackendRegistry: Global registry for discovering and managing backends
- Tool naming: {system}_{action} (e.g., kingdee_query_bill, sap_query_bill)
"""

import functools
import logging
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Type, runtime_checkable

logger = logging.getLogger(__name__)

# ── Request ID Framework ─────────────────────────────────────────
# 框架级 request_id 注入：所有后端工具函数统一包装，
# 一次生成 UUID → ContextVar 传播 → Filter 自动注入日志 → 审计日志关联。
# 新增 ERP 后端时无需关心 request_id，框架自动处理。

_current_request_id: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    """Auto-inject request_id into all log records from ContextVar.

    Add to any logging.Handler to automatically include %(request_id)s
    in log output. Falls back to "-" when no request is active.
    """

    def filter(self, record):
        record.request_id = _current_request_id.get("") or "-"
        return True


def with_request_id(tool_name: str):
    """Wrap a tool function with automatic request_id injection.

    Per-call lifecycle:
    1. Generate uuid4().hex[:12] as request_id
    2. Store in ContextVar (propagates to all loggers via RequestIdFilter)
    3. Log start/finish with request_id
    4. Reset ContextVar on exit

    Applied at registration time in backend.register_tools(), NOT on
    individual tool functions. New backends just register raw functions.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            req_id = uuid.uuid4().hex[:12]
            token = _current_request_id.set(req_id)
            logger.info("[%s] >>> %s", req_id, tool_name)
            try:
                return await func(*args, **kwargs)
            finally:
                logger.info("[%s] <<< %s", req_id, tool_name)
                _current_request_id.reset(token)
        return wrapper
    return decorator


def get_current_request_id() -> str:
    """Get the current request_id from ContextVar (for audit_log etc.)."""
    return _current_request_id.get("") or ""


@runtime_checkable
class ERPBackend(Protocol):
    """Protocol defining the interface for ERP system backends.
    
    All ERP backends (Kingdee, SAP, Oracle, etc.) must implement this protocol
    to be registered and used within the unified plugin architecture.
    
    Required attributes:
        system_name: Unique identifier (e.g., "kingdee", "sap")
        display_name: Human-readable name (e.g., "金蝶云星空")
        config_fields: List of QwenPaw config field definitions
        domains: Dict mapping domain names to FormId prefixes
    
    Required methods:
        register_tools: Register backend-specific tools with QwenPaw API
        register_routes: Register backend-specific HTTP routes (optional)
        get_client: Get or create the backend API client
    """
    
    # ---- Required Attributes ----
    
    @property
    def system_name(self) -> str:
        """Unique system identifier (lowercase, no spaces)."""
        ...
    
    @property
    def display_name(self) -> str:
        """Human-readable display name for UI."""
        ...
    
    @property
    def label(self) -> str:
        """Short label for UI tabs (e.g., '金蝶', '用友')."""
        ...
    
    @property
    def config_fields(self) -> List[Dict[str, Any]]:
        """QwenPaw config field definitions for this backend.
        
        Returns:
            List of dicts with keys: name, label, type, required, placeholder, help
        """
        ...
    
    @property
    def domains(self) -> Dict[str, List[str]]:
        """Business domain to FormId prefix mapping.
        
        Returns:
            Dict like {"finance": ["GL_", "AR_", "AP_"], "sales": ["SAL_"]}
        """
        ...
    
    # ---- Required Methods ----
    
    def register_tools(self, api: "PluginApi") -> int:
        """Register all backend-specific tools with QwenPaw.
        
        Tool naming convention: {system_name}_{action}
        Example: kingdee_query_bill, sap_save_bill
        
        Args:
            api: QwenPaw PluginApi instance
            
        Returns:
            Number of tools registered
        """
        ...
    
    def register_routes(self, api: "PluginApi") -> None:
        """Register backend-specific HTTP routes (optional).
        
        Used for admin UI, webhooks, etc.
        
        Args:
            api: QwenPaw PluginApi instance
        """
        ...
    
    def get_client(self, config: Dict[str, Any]) -> Any:
        """Get or create the backend API client.
        
        Args:
            config: Configuration dict from get_tool_config()
            
        Returns:
            Backend-specific client instance
        """
        ...
    
    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test connection with the given config.

        Args:
            config: Configuration dict for this backend

        Returns:
            Dict with: success (bool), message (str), details (optional dict)
        """
        ...

    def get_metadata_dir(self) -> Optional[Path]:
        """Get the path to this backend's metadata directory.
        
        Returns:
            Path to metadata directory, or None if not applicable
        """
        ...
    
    def get_health_check_tool(self) -> Optional[str]:
        """Get the tool name to use for health check config lookup.
        
        Returns:
            Tool name string (e.g., "kingdee_query_bill"), or None
        """
        ...


class BackendRegistry:
    """Global registry for ERP backends.
    
    Usage:
        # Register a backend
        registry.register(KingdeeBackend())
        
        # Get a backend by name
        backend = registry.get("kingdee")
        
        # List all registered backends
        for name in registry.list_all():
            print(name)
    """
    
    def __init__(self):
        self._backends: Dict[str, ERPBackend] = {}
    
    def register(self, backend: ERPBackend) -> None:
        """Register a backend instance.
        
        Args:
            backend: Backend instance implementing ERPBackend protocol
            
        Raises:
            ValueError: If backend.system_name already registered
        """
        name = backend.system_name
        if name in self._backends:
            raise ValueError(f"Backend '{name}' already registered")
        self._backends[name] = backend
        logger.info(f"Registered ERP backend: {name} ({backend.display_name})")
    
    def get(self, system_name: str) -> Optional[ERPBackend]:
        """Get a backend by system name.
        
        Args:
            system_name: Backend identifier (e.g., "kingdee")
            
        Returns:
            Backend instance or None if not found
        """
        return self._backends.get(system_name)
    
    def list_all(self) -> List[str]:
        """List all registered backend names."""
        return list(self._backends.keys())
    
    def get_all(self) -> Dict[str, ERPBackend]:
        """Get all registered backends."""
        return self._backends.copy()
    
    def get_all_domains(self) -> Dict[str, List[str]]:
        """Get merged domain mappings from all backends.
        
        Returns:
            Dict like {"kingdee:finance": ["GL_", "AR_"], "sap:finance": [...]}
        """
        result = {}
        for name, backend in self._backends.items():
            for domain, prefixes in backend.domains.items():
                # Use prefixed key for multi-system support
                prefixed_key = f"{name}:{domain}"
                result[prefixed_key] = prefixes
                # Also support unprefixed for backward compatibility
                if domain not in result:
                    result[domain] = prefixes
        return result


# Global singleton registry
registry = BackendRegistry()


def get_registry() -> BackendRegistry:
    """Get the global backend registry."""
    return registry
