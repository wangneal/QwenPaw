# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""System prompt building utilities.

This module provides utilities for building system prompts from
markdown configuration files in the working directory.
"""
import logging
import re
from pathlib import Path

from agentscope_runtime.engine.schemas.exception import (
    ConfigurationException,
)

from .memory.base_memory_manager import BaseMemoryManager
from .utils.file_handling import read_text_file_with_encoding_fallback

logger = logging.getLogger(__name__)

# Default fallback prompt
DEFAULT_SYS_PROMPT = """
You are a helpful assistant.
"""

# Backward compatibility alias
SYS_PROMPT = DEFAULT_SYS_PROMPT


class PromptConfig:
    """Configuration for system prompt building."""

    # Default files to load when no config is provided
    # All files are optional - if they don't exist, they'll be skipped
    DEFAULT_FILES = [
        "AGENTS.md",
        "SOUL.md",
        "PROFILE.md",
    ]


class PromptBuilder:
    """Builder for constructing system prompts from markdown files."""

    # Regex pattern to match heartbeat section markers
    HEARTBEAT_PATTERN = re.compile(
        r"<!-- heartbeat:start -->.*?<!-- heartbeat:end -->",
        re.DOTALL,
    )

    # Regex pattern to match memory section markers
    MEMORY_PATTERN = re.compile(
        r"<!-- memory:start -->.*?<!-- memory:end -->",
        re.DOTALL,
    )

    def __init__(
        self,
        working_dir: Path,
        enabled_files: list[str] | None = None,
        heartbeat_enabled: bool = False,
        language: str = "zh",
        memory_manager: BaseMemoryManager | None = None,
    ):
        """Initialize prompt builder.

        Args:
            working_dir: Directory containing markdown configuration files
            enabled_files: List of filenames to load (if None, uses default order)
            heartbeat_enabled: Whether heartbeat is enabled, affects AGENTS.md content
            language: Language code used to select the memory prompt.
            memory_manager: Memory manager instance for generating memory prompts.
        """
        self.working_dir = working_dir
        self.enabled_files = enabled_files
        self.heartbeat_enabled = heartbeat_enabled
        self.language = language
        self.memory_manager = memory_manager
        self.prompt_parts = []
        self.loaded_count = 0

    def _load_file(self, filename: str) -> None:
        """Load a single markdown file.

        All files are optional - if they don't exist or can't be read,
        they will be silently skipped.

        Args:
            filename: Name of the file to load
        """
        file_path = self.working_dir / filename

        if not file_path.exists():
            logger.debug("File %s not found, skipping", filename)
            return

        try:
            content = read_text_file_with_encoding_fallback(file_path).strip()

            # Remove YAML frontmatter if present
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()

            # Filter heartbeat / memory sections from AGENTS.md based on config
            if filename == "AGENTS.md":
                try:
                    content = self._process_heartbeat_section(content)
                except Exception as e:
                    logger.warning(
                        f"Failed to process heartbeat with {e}",
                    )
                try:
                    content = self._process_memory_section(content)
                except Exception as e:
                    logger.warning(
                        f"Failed to process memory section with {e}",
                    )

            if content:
                if self.prompt_parts:  # Add separator if not first section
                    self.prompt_parts.append("")
                # Add section header with filename
                self.prompt_parts.append(f"# {filename}")
                self.prompt_parts.append("")
                self.prompt_parts.append(content)
                self.loaded_count += 1
                logger.debug("Loaded %s", filename)
            else:
                logger.debug("Skipped empty file: %s", filename)

        except Exception as e:
            logger.warning(
                "Failed to read file %s: %s, skipping",
                filename,
                e,
            )

    def _process_heartbeat_section(self, content: str) -> str:
        """Process heartbeat section in AGENTS.md content.

        - If heartbeat markers not found: keep content unchanged (backward compatibility)
        - If heartbeat is enabled: keep the content but remove the markers
        - If heartbeat is disabled: remove the entire section

        Args:
            content: Original AGENTS.md content

        Returns:
            Processed content
        """
        # Check if markers exist
        if "<!-- heartbeat:start -->" not in content:
            return content

        if self.heartbeat_enabled:
            # Keep content, just remove the markers
            content = content.replace("<!-- heartbeat:start -->", "")
            content = content.replace("<!-- heartbeat:end -->", "")
            return content.strip()
        else:
            # Remove the entire heartbeat section
            filtered = self.HEARTBEAT_PATTERN.sub("", content)
            return filtered.strip()

    def _process_memory_section(self, content: str) -> str:
        """Process memory section in AGENTS.md content.

        - If memory markers are found: remove the entire section.
        - Always append the canonical memory prompt at the end.

        Args:
            content: Original AGENTS.md content

        Returns:
            Processed content with memory prompt appended.
        """
        # Remove existing memory section if markers exist
        if "<!-- memory:start -->" in content:
            content = self.MEMORY_PATTERN.sub("", content).strip()

        # Get memory prompt from manager or fallback
        if self.memory_manager:
            memory_section = self.memory_manager.get_memory_prompt(
                self.language,
            )
        else:
            memory_section = ""

        return (
            (content + "\n\n" + memory_section).strip()
            if content
            else memory_section
        )

    def build(self) -> str:
        """Build the system prompt from markdown files.

        All files are optional. If no files can be loaded, returns the default prompt.

        Returns:
            Constructed system prompt string
        """
        # Determine which files to load
        files_to_load = (
            PromptConfig.DEFAULT_FILES
            if self.enabled_files is None
            else self.enabled_files
        )

        # Load all files (all are optional)
        for filename in files_to_load:
            self._load_file(filename)

        if not self.prompt_parts:
            logger.warning("No content loaded from working directory")
            return DEFAULT_SYS_PROMPT

        # Join all parts with double newlines
        final_prompt = "\n\n".join(self.prompt_parts)

        logger.debug(
            "System prompt built from %d file(s), total length: %d chars",
            self.loaded_count,
            len(final_prompt),
        )

        return final_prompt


def build_system_prompt_from_working_dir(
    working_dir: Path | None = None,
    enabled_files: list[str] | None = None,
    agent_id: str | None = None,
    heartbeat_enabled: bool = False,
    language: str = "zh",
    memory_manager: BaseMemoryManager | None = None,
) -> str:
    """
    Build system prompt by reading markdown files from working directory.

    This function constructs the system prompt by loading markdown files from
    the specified working directory (workspace_dir for multi-agent setup).
    These files define the agent's behavior, personality, and operational guidelines.

    The files to load are determined by the enabled_files parameter or
    agents.system_prompt_files configuration. If not configured, falls back to
    default files:
    - AGENTS.md - Detailed workflows, rules, and guidelines
    - SOUL.md - Core identity and behavioral principles
    - PROFILE.md - Agent identity and user profile

    All files are optional. If a file doesn't exist or can't be read, it will be
    skipped. If no files can be loaded, returns the default prompt.

    Args:
        working_dir: Directory to read markdown files from (if None, uses
            global WORKING_DIR for backward compatibility)
        enabled_files: List of filenames to load (if None, uses config or defaults)
        agent_id: Agent identifier to include in system prompt (optional)
        heartbeat_enabled: Whether heartbeat is enabled. When False, filters
            heartbeat section from AGENTS.md to avoid confusing instructions.
        language: Language code (``"zh"`` or ``"en"``) for memory prompt.
        memory_manager: Memory manager instance for generating memory prompts.
            If provided, uses its ``get_memory_prompt()`` method instead of
            the standalone function.

    Returns:
        str: Constructed system prompt from markdown files.
             If no files exist, returns the default prompt.

    Example:
        If working_dir contains AGENTS.md, SOUL.md and PROFILE.md, they will be combined:
        "# AGENTS.md\\n\\n...\\n\\n# SOUL.md\\n\\n...\\n\\n# PROFILE.md\\n\\n..."
    """
    from ..constant import WORKING_DIR
    from ..config import load_config

    # Use provided working_dir or fallback to global WORKING_DIR
    if working_dir is None:
        working_dir = Path(WORKING_DIR)

    # Load enabled files from parameter or config
    if enabled_files is None:
        # Use agent-specific config if agent_id provided
        if agent_id:
            from ..config.config import load_agent_config

            try:
                agent_config = load_agent_config(agent_id)
                enabled_files = agent_config.system_prompt_files
            except (ValueError, FileNotFoundError, ConfigurationException):
                # Agent not found in config, fallback to global config
                config = load_config()
                enabled_files = config.agents.system_prompt_files
        else:
            # Fallback to global config for backward compatibility
            config = load_config()
            enabled_files = config.agents.system_prompt_files

    # P2.3: 根据配置选择 compact / full 构建器
    if _use_compact_prompt(config):
        builder = CompactPromptBuilder(
            working_dir=working_dir,
            enabled_files=enabled_files,
            heartbeat_enabled=heartbeat_enabled,
            language=language,
            memory_manager=memory_manager,
        )
    else:
        builder = PromptBuilder(
            working_dir=working_dir,
            enabled_files=enabled_files,
            heartbeat_enabled=heartbeat_enabled,
            language=language,
            memory_manager=memory_manager,
        )
    prompt = builder.build()

    # Add agent identity information at the beginning of the prompt
    if agent_id:
        identity_header = (
            f"# Agent Identity\n\n"
            f"Your agent id is `{agent_id}`. "
            f"This is your unique identifier in the multi-agent system.\n\n"
        )
        prompt = identity_header + prompt

    return prompt


def build_bootstrap_guidance(
    language: str = "zh",
) -> str:
    """Build bootstrap guidance message for first-time setup.

    Args:
        language: Language code (zh/en/ru)

    Returns:
        Formatted bootstrap guidance message
    """
    if language == "zh":
        return (
            "# 引导模式\n"
            "\n"
            "工作目录中存在 `BOOTSTRAP.md` — 首次设置。\n"
            "\n"
            "1. 阅读 BOOTSTRAP.md，友好地表示初次见面，"
            "引导用户完成设置。\n"
            "2. 按照 BOOTSTRAP.md 的指示，"
            "帮助用户定义你的身份和偏好。\n"
            "3. 按指南创建/更新必要文件"
            "（PROFILE.md、MEMORY.md 等）。\n"
            "4. 完成后删除 BOOTSTRAP.md。\n"
            "\n"
            "如果用户希望跳过，直接回答下面的问题即可。\n"
            "\n"
            "---\n"
            "\n"
        )
    # en / ru / other — default to English
    return (
        "# BOOTSTRAP MODE\n"
        "\n"
        "`BOOTSTRAP.md` exists — first-time setup.\n"
        "\n"
        "1. Read BOOTSTRAP.md, greet the user, "
        "and guide them through setup.\n"
        "2. Follow BOOTSTRAP.md instructions "
        "to define identity and preferences.\n"
        "3. Create/update files "
        "(PROFILE.md, MEMORY.md, etc.) as described.\n"
        "4. Delete BOOTSTRAP.md when done.\n"
        "\n"
        "If the user wants to skip, answer their "
        "question directly instead.\n"
        "\n"
        "---\n"
        "\n"
    )


def _get_active_model_info():
    """Resolve the active model's ModelInfo and model name.

    Tries agent-specific model first, then falls back to global.

    Returns:
        A ``(ModelInfo, model_name)`` tuple.  Both elements are *None*
        when the active model cannot be resolved.
    """
    try:
        from ..app.agent_context import get_current_agent_id
        from ..config.config import load_agent_config
        from ..providers.provider_manager import ProviderManager

        manager = ProviderManager.get_instance()

        # Try to get agent-specific model first
        active = None
        try:
            agent_id = get_current_agent_id()
            agent_config = load_agent_config(agent_id)
            if agent_config.active_model:
                active = agent_config.active_model
        except Exception:
            pass

        # Fallback to global active model
        if not active:
            active = manager.get_active_model()

        if not active:
            return None, None

        provider = manager.get_provider(active.provider_id)
        if not provider:
            return None, None

        for m in provider.models + provider.extra_models:
            if m.id == active.model:
                return m, active.model
        return None, None
    except Exception:
        return None, None


def get_active_model_supports_multimodal() -> bool:
    """Check if the current active model supports multimodal input."""
    model_info, _ = _get_active_model_info()
    if model_info is None:
        return False
    return bool(model_info.supports_multimodal)


def get_active_model_multimodal_raw() -> bool | None:
    """Return the effective multimodal capability flag for the active model.

    Checks ``supports_multimodal``, ``supports_image``, and
    ``supports_video`` — any of them being ``True`` means multimodal
    is confirmed.

    - ``True``: confirmed multimodal support (via any of the three flags)
    - ``False``: confirmed text-only (supports_multimodal is explicitly
      False and neither supports_image nor supports_video is True)
    - ``None``: unknown / not yet probed (all three are None)
    """
    model_info, _ = _get_active_model_info()
    if model_info is None:
        return None
    if model_info.supports_image or model_info.supports_video:
        return True
    return model_info.supports_multimodal


def build_multimodal_hint() -> str:
    """Build a short system-prompt snippet describing multimodal capability."""
    model_info, model_name = _get_active_model_info()
    if model_info is None:
        return ""
    return format_multimodal_hint(model_info, model_name)


def format_multimodal_hint(model_info, _model_name: str) -> str:
    """Format the multimodal hint string for the system prompt."""
    if (
        model_info.supports_image
        or model_info.supports_video
        or model_info.supports_multimodal is None
    ):
        return ""
    return (
        "It appears that you can only understand text content. "
        " Please honestly inform the user about this when "
        " their input includes multimodal information."
    )


__all__ = [
    "build_system_prompt_from_working_dir",
    "build_bootstrap_guidance",
    "build_multimodal_hint",
    "format_multimodal_hint",
    "get_active_model_supports_multimodal",
    "get_active_model_multimodal_raw",
    "PromptBuilder",
    "PromptConfig",
    "CompactPromptBuilder",  # [NEW]
    "CITATION_RULE",         # [NEW]
    "DEFAULT_SYS_PROMPT",
    "SYS_PROMPT",
]


# ======================================================================
# P2.3 / P2.4 — CompactPromptBuilder + CITATION_RULE
# ======================================================================

# P2.4: 引用溯源规则
CITATION_RULE = """
## 引用规则（强制）

当你的回答基于以下来源时，必须标注出处：
- 基于记忆检索结果 -> 标注 [来源:记忆]
- 基于工具查询结果 -> 标注 [来源:工具名]
- 基于技能知识文档 -> 标注 [来源:技能名]
- 基于你自己的推理/知识 -> 标注 [来源:推理]

示例："该供应商编码是 S001 [来源:kingdee_query_bill]"
未标注来源的回答将被标记为【未验证】。
"""

# AGENTS.md 入口点摘要行数上限（约 800 token）
_ENTRY_POINT_LINE_LIMIT = 40


class CompactPromptBuilder(PromptBuilder):
    """两阶段构建的提示词构建器 — 仅注入入口点，节省 token。

    阶段1（始终注入）:
    - SOUL.md 全量 — 身份定义不宜拆分
    - PROFILE.md 全量 — 通常简短
    - AGENTS.md 摘要 — 前 40 行的核心规则（约 800 token）
    - CITATION_RULE — 引用溯源规则

    阶段2（按需注入，通过 pre_reasoning hook）:
    - SKILL.md — 只在触发对应技能时注入
    - AGENTS.md 完整版 — 通过 read_file 按需加载

    使用方法：在配置中设置 ``system_prompt_mode: "compact"``。
    默认 ``"full"`` 保留原有 PromptBuilder 行为，向后兼容。
    """

    def __init__(
        self,
        working_dir: Path,
        enabled_files: list[str] | None = None,
        heartbeat_enabled: bool = False,
        language: str = "zh",
        memory_manager: BaseMemoryManager | None = None,
    ):
        super().__init__(
            working_dir=working_dir,
            enabled_files=enabled_files,
            heartbeat_enabled=heartbeat_enabled,
            language=language,
            memory_manager=memory_manager,
        )

    def _load_file(self, filename: str) -> None:
        """加载单个文件——全量加载（保留父类行为）。"""
        # AGENTS.md 仅加载入口点摘要
        if filename == "AGENTS.md":
            self._load_agents_entry_point()
            return
        super()._load_file(filename)

    def _load_agents_entry_point(self) -> None:
        """加载 AGENTS.md 的前 N 行作为入口点摘要。"""
        file_path = self.working_dir / "AGENTS.md"
        if not file_path.exists():
            logger.debug("AGENTS.md not found, skipping entry point")
            return

        try:
            from .utils.file_handling import read_text_file_with_encoding_fallback

            full_content = read_text_file_with_encoding_fallback(
                file_path,
            ).strip()
            if not full_content:
                return

            # 取前 N 行作为摘要
            lines = full_content.split("\n")
            entry_lines = lines[:_ENTRY_POINT_LINE_LIMIT]
            entry_content = "\n".join(entry_lines).strip()

            if entry_content:
                if self.prompt_parts:
                    self.prompt_parts.append("")
                self.prompt_parts.append("# AGENTS.md（核心规则摘要）")
                self.prompt_parts.append("")
                self.prompt_parts.append(entry_content)
                self.prompt_parts.append("")
                self.prompt_parts.append(
                    "> 完整 AGENTS.md 可通过 read_file(\"AGENTS.md\") 查看。"
                )
                self.loaded_count += 1
                logger.debug(
                    "Loaded AGENTS.md entry point (%d/%d lines)",
                    len(entry_lines),
                    len(lines),
                )
        except Exception as e:
            logger.warning("Failed to load AGENTS.md entry point: %s", e)

    def build(self) -> str:
        """构建系统提示词 — 全量 SOUL.md + PROFILE.md + AGENTS.md 摘要。"""
        # 加载指定文件列表
        files_to_load = (
            PromptConfig.DEFAULT_FILES
            if self.enabled_files is None
            else self.enabled_files
        )
        for filename in files_to_load:
            self._load_file(filename)

        # 追加引用溯源规则
        self.prompt_parts.append("")
        self.prompt_parts.append(CITATION_RULE.strip())

        if not self.prompt_parts:
            logger.warning("No content loaded from working directory")
            return DEFAULT_SYS_PROMPT

        final_prompt = "\n\n".join(self.prompt_parts)
        logger.debug(
            "Compact prompt built from %d file(s), total length: %d chars",
            self.loaded_count,
            len(final_prompt),
        )
        return final_prompt


def _use_compact_prompt(config: Any) -> bool:
    """检查配置是否启用 compact 模式。"""
    try:
        mode = getattr(config.agents, "system_prompt_mode", "full")
        return mode == "compact"
    except Exception:
        return False
