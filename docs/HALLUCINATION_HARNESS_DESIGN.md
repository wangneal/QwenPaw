# QwenPaw 幻觉驾驭层设计文档 (Harness Engineering)

> **文档状态**: DRAFT v1.0
> **最后更新**: 2026-06-04
> **范式参考**: [Harness Engineering](https://www.runoob.com/ai-agent/harness-engineering.html)

---

## 1. 背景与动机

### 1.1 问题描述

QwenPaw 是一个基于 ReAct Agent 架构的个人 AI 助手，使用 agentscope 框架。LLM 产生以下类型的幻觉：

| 幻觉类型 | 具体表现 | 严重程度 |
|----------|----------|----------|
| 纯文本编造 | 编造事实、虚构数据、无中生有 | 高 |
| 工具参数幻觉 | 编造文件路径、虚构 FormId、猜测编码值 | 高 |
| 空结果编造 | 工具查询返回空后，LLM 自行编造后续答案 | 高 |
| 知识冲突 | 检索到 A 但 LLM 用内部知识回答相反结果 | 中 |
| 跨工具链幻觉 | 多步调用中编造中间步骤的输出 | 中 |
| 文档腐烂 | 技能文档/记忆与实际代码/API 不一致 | 中 |

### 1.2 为什么 Prompt 约束不够

已验证结论：系统提示词中的"不要幻觉"等指令，LLM 可以且会忽略。原因：

1. LLM 的注意力机制无法保证对任意指令的持久遵守
2. 长对话中指令的约束力随上下文增长而衰减
3. 工具调用的参数生成是 token 级别的，不受语义级指令约束

### 1.3 已有验证：金蝶 ERP 插件的代码级防护

金蝶 ERP 插件 (`plugins/tool/kingdee-erp/`) 已实现一套代码级强制防护：

| 防护手段 | 实现方式 | LLM能否绕过 |
|----------|----------|------------|
| FormId 白名单 | `_is_valid_form_id()` 从 JSON 元数据加载，非法直接拒绝 | 不能 |
| 双步调用 | `execute=False` 预览后 `execute=True` 执行 | 不能 |
| 防跳步指纹 | `_preview_key()` + MD5 指纹校验，未预览则拒绝执行 | 不能 |
| 空结果声明 | 查询返回空时硬编码追加"不要编造替代答案" | 可忽略但降低概率 |

**关键洞察**：这些防护全部在工具函数内部（代码层），不依赖 LLM 遵守 prompt。现在需将这套模式**从 ERP 插件提升到 Agent 框架层**。

### 1.4 为什么采用 Harness Engineering 范式

Mitchell Hashimoto 核心论点：

> "任何时候你发现 Agent 犯了一个错误，你应该花时间去工程化一个解决方案，使得 Agent 在未来不会再犯同样的错误。"

Harness Engineering 提供四个系统性护栏：

| 护栏 | 作用 | 类比 |
|------|------|------|
| 上下文工程 | 精确控制 Agent 看到什么 | 新员工手册 |
| 架构约束 | 代码级强制，LLM 无法绕过 | 缰绳 |
| 反馈循环 | 发现错误后自动修正，而非仅拦截 | 智能体审智能体 |
| 熵管理 | 持续清理腐烂知识，防止债务累积 | 垃圾回收 |

---

## 2. QwenPaw 现有架构分析

### 2.1 Agent 调用链路

```
用户输入
  |
  v
QwenPawAgent.reply()
  |
  v
Hook: pre_reply      -> 自动记忆检索 (auto_memory_search)
  |
  v
Hook: pre_reasoning  -> 上下文压缩 (context_compression)
  |
  v
ReAct 循环:
  +-- _reasoning()   -> LLM 生成 text / tool_use
  +-- _acting()      -> 执行工具调用 -> tool_result
  +-- 循环直到 LLM 输出纯文本回复
  |
  v
Hook: post_reply     -> 自动记忆存储 (auto_memory_save)
  |
  v
返回给用户
```

### 2.2 Agent MRO 继承链

```python
class QwenPawAgent(
    CodingModeMixin,      # 编码模式增强
    ToolGuardMixin,       # 工具调用守卫
    ReActAgent,           # agentscope ReAct 基类
):
    ...
```

改造后 MRO（新增 HallucinationGuardMixin）：

```python
class QwenPawAgent(
    HallucinationGuardMixin,  # [NEW] 幻觉防护 Mixin
    CodingModeMixin,
    ToolGuardMixin,
    ReActAgent,
):
    ...
```

### 2.3 提示词构建流程

当前 `prompt.py` 的 PromptBuilder 全量加载所有文档到系统提示词，占用大量 token 空间，挤占任务可用上下文窗口。

### 2.4 关键 Hook 点位

| Hook | 时机 | 当前用途 | 可扩展用途 |
|------|------|----------|-----------|
| `pre_reply` | reply() 开始前 | 自动记忆检索 | 知识冲突检测、动态上下文注入 |
| `pre_reasoning` | 每轮推理前 | 上下文压缩 | 按需技能文档注入 |
| `post_reply` | reply() 结束后 | 自动记忆存储 | Agent 自审、引用校验 |
| `post_acting` | 每次工具执行后 | 工具结果裁剪 | 空结果声明、置信度标注 |
| `post_reply` | reply() 结束 | 自动记忆存储 | 知识冲突代码级检测、Agent 自审 |

---

## 3. 设计方案：四护栏驾驭层

### 整体架构

```
+----------------------- QwenPaw Harness Layer -----------------------+
|                                                                       |
|  护栏一: 上下文工程 (Context Engineering)                              |
|  +-- 活文档入口点模式 -- PromptBuilder 两阶段构建                       |
|  +-- 技能文档按需注入 -- pre_reasoning hook 动态加载                    |
|  +-- 记忆动态检索注入 -- pre_reply hook 主题相关记忆                    |
|  +-- 引用溯源标记 -- 上下文中标注信息来源 [来源:xxx]                     |
|                                                                       |
|  护栏二: 架构约束 (Architecture Constraints)                          |
|  +-- L0 代码强制 -- 双步调用、白名单校验                                 |
|  +-- L1 Schema 强制 -- Pydantic 校验 tool_call 参数                    |
|  +-- L2 Mixin 拦截 -- HallucinationGuardMixin 路径/编码值校验          |
|  +-- L3 后处理注入 -- 空结果防幻觉声明、置信度标注                       |
|  +-- L4 Prompt 引导 -- 仅作辅助，不依赖                                 |
|                                                                       |
|  护栏三: 反馈循环 (Feedback Loop)                                     |
|  +-- 幻觉拦截 -> 修正引导 -- 拦截后注入具体修正上下文                    |
|  +-- Agent 自审 -- post_reply 事实性声明自校验                          |
|  +-- 自审修正循环 -- 发现幻觉后自动追加修正声明                         |
|  +-- 拦截原因教学化 -- 错误信息解释为什么+正确做法                       |
|                                                                       |
|  护栏四: 熵管理 (Entropy Management)                                  |
|  +-- Doc-gardening Agent -- 定期扫描技能文档腐烂                        |
|  +-- Dream 增强 -- 记忆事实性校验 + 幻觉溯源标记                        |
|  +-- 架构漂移扫描 -- 后台 Agent 检测代码坏模式蔓延                      |
|  +-- 持续小额偿还 -- 技术债务不累积，发现即修正                         |
|                                                                       |
+-----------------------------------------------------------------------+
```

---

## 4. 护栏一：上下文工程 (Context Engineering)

### 4.1 设计原则

> 上下文是稀缺资源。巨大的指令文件挤掉任务空间。

### 4.2 活文档入口点模式

**当前问题**：`AGENTS.md` / `SOUL.md` / `PROFILE.md` 全量加载进系统提示词。

**改造方案**：PromptBuilder 改为两阶段构建

```
阶段1: 核心身份 + 规则入口点 (始终注入, < 800 token)
  +-- Agent 身份定义 (SOUL.md -- 保留全量，身份不宜拆分)
  +-- 用户画像 (PROFILE.md -- 保留全量，通常简短)
  +-- 核心规则入口点 (从 AGENTS.md 提取 < 800 token 摘要)
  +-- 工具列表 (仅名称 + 一句话描述，不含详细参数)

阶段2: 按需注入 (pre_reasoning hook 动态加载)
  +-- 技能文档 (SKILL.md -- 只在触发对应技能时注入)
  +-- 详细规则 (AGENTS.md 完整版 -- 需要 read_file 加载)
  +-- 领域知识 (只在对话涉及特定领域时注入)
```

**阶段1 入口点示例**：

```markdown
## 核心规则摘要

1. 先查询再回答 -- 事实性问题必须通过工具验证
2. 不猜测编码值 -- 使用查询工具获取真实编码
3. 写入必须预览 -- 所有写入操作 execute=False 先预览
4. 标注信息来源 -- 事实性声明标注 [来源:xxx]

详细规则请通过 read_file("AGENTS.md") 查看。
技能文档在触发对应技能时自动加载。
```

**实现文件**：`src/qwenpaw/agents/prompt.py` — `PromptBuilder` 改造

### 4.3 技能文档按需注入

**实现位置**：`pre_reasoning` hook（`light_context_manager.py`）

```python
async def pre_reasoning(
    self, agent: Any, kwargs: dict[str, Any]
) -> dict[str, Any] | None:
    """推理前：按需注入技能文档。

    注意：BaseContextManager hook 签名接收 kwargs: dict，不是 msg: Msg。
    需要从 kwargs 中提取 msg。
    """
    msg = kwargs.get("msg") or kwargs.get("messages")
    if msg is None:
        return None

    # 1. 上下文压缩（原有逻辑）
    compressed = await self._compress_context(agent.memory)

    # 2. 技能文档按需注入（新增）
    # TODO: _detect_active_skills 需实现，从消息内容中识别涉及哪些技能
    current_skills = self._detect_active_skills(msg)
    for skill_id in current_skills:
        if skill_id not in agent._loaded_skills:
            # TODO: _load_skill_doc 需实现，从 skills/{skill_id}/SKILL.md 加载
            skill_doc = await self._load_skill_doc(skill_id)
            agent.memory.add(Msg(role="system", content=skill_doc))
            agent._loaded_skills.add(skill_id)

    return compressed
```

### 4.4 记忆动态检索注入

**当前问题**：`pre_reply` 的 `auto_memory_search` 是全量检索，可能注入不相关记忆。

**改造方案**：基于对话主题的相关性检索

```python
async def pre_reply(
    self, agent: Any, kwargs: dict[str, Any]
) -> dict[str, Any] | None:
    """回复前：基于对话主题检索相关记忆。

    注意：实际 hook 签名是 kwargs: dict，需从中提取 msg。
    """
    msg = kwargs.get("msg") or kwargs.get("messages")
    if msg is None:
        return None

    # 1. 从用户消息中提取关键词/主题
    # TODO: _extract_topics 需实现
    topics = self._extract_topics(msg)

    # 2. 按主题相关性检索记忆（而非全量）
    # TODO: 确认 agentscope InMemoryMemory.search() API 是否支持 min_relevance
    relevant_memories = await self.memory.search(
        query=topics, top_k=5,
    )
    if relevant_memories:
        # 3. 注入记忆时同时注入冲突检测（代码级 + prompt 级）
        memory_context = self._format_memories(relevant_memories)
        agent.memory.add(Msg(
            role="system",
            content=memory_context + "\n\n" + CONFLICT_DETECTION_INSTRUCTION,
        ))
```

### 4.5 知识冲突检测指令

> ⚠️ **设计说明**：本节是 L4 Prompt 级约束，属于辅助层。
> 真正的代码级强制在 **§6.3 的 `post_reply` hook** 中实现
>（检测 LLM 回复与检索记忆是否矛盾，矛盾则代码强制追加修正声明）。
> 这里的 prompt 指令是补充，不依赖其作为唯一防护。

**实现位置**：`pre_reply` hook（记忆注入时追加）

```python
CONFLICT_DETECTION_INSTRUCTION = """
【知识冲突规则 -- 强制】
上方检索到的记忆/知识是经过验证的真实数据。
如果你的内部知识与检索结果矛盾，必须以检索结果为准。
禁止用内部知识覆盖或否定检索结果。
如果检索结果为空，必须声明"未找到相关记录"，不得用内部知识填充。
"""
```

### 4.6 引用溯源标记

在系统提示词入口点中注入强制引用规则，后处理检测见 6.4 节。

```python
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
```
---
## 5. 护栏二：架构约束 (Architecture Constraints)

### 5.1 设计原则

约束必须自动化，编码为代码/Linter/CI。L0-L2 硬性约束 LLM 无法绕过。

### 5.2 约束层级模型

| 级别 | 约束方式 | LLM能否绕过 | 实现位置 |
|------|----------|------------|----------|
| L0 代码强制 | 函数内部硬逻辑 | 不能 | 工具函数内部 |
| L1 Schema 强制 | inspect/Pydantic 校验参数 | 不能 | _acting() 入口 |
| L2 Mixin 拦截 | MRO 钩子拦截 | 不能 | HallucinationGuardMixin._acting() |
| L3 后处理注入 | tool_result 后追加 | 可忽略但降概率 | post_acting hook |
| L4 Prompt 引导 | 系统提示词中的规则 | 可被忽略 | prompt.py |

关键防幻觉手段必须在 L0-L2 实现。

### 5.3 L0 代码强制 - AntiHallucinationToolMixin

```python
import asyncio
import hashlib
import json


class AntiHallucinationToolMixin:
    """工具防幻觉基类 — 所有工具可继承获得 L0 防护能力。"""

    PARAM_WHITELISTS: dict[str, set[str]] = {}
    REQUIRES_PREVIEW: bool = False
    DECLARE_EMPTY_RESULT: bool = False

    def __init__(self):
        self._preview_lock = asyncio.Lock()
        self._previewed_keys: set[str] = set()

    async def enforce_two_step(self, execute: bool, params: dict) -> dict | None:
        """强制双步调用：未预览则拒绝执行。"""
        pkey = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        if not execute:
            async with self._preview_lock:
                self._previewed_keys.add(pkey)
            return {"preview": params, "status": "pending"}
        async with self._preview_lock:
            if pkey not in self._previewed_keys:
                return {"error": "请先预览(execute=False)确认后再执行(execute=True)"}
        return None

    async def declare_if_empty(self, results: list | dict, tool_name: str) -> str | None:
        """查询结果为空时返回防幻觉声明。"""
        if not results:
            return f"【{tool_name} 返回空结果】请核实查询条件，不要编造替代答案"
        return None
```

金蝶改造：`_is_valid_form_id` → `PARAM_WHITELISTS["form_id"]`, `_check_previewed` → `enforce_two_step()`

### 5.4 L1 Schema 强制

```python
import inspect


def _validate_tool_input(tool_fn, tool_input: dict) -> list[str]:
    """校验工具输入是否符合函数签名定义的 schema。
    宽松策略：int("5") 通过，int("abc") 才失败。
    """
    violations = []
    sig = inspect.signature(tool_fn)
    for name, param in sig.parameters.items():
        if name in tool_input:
            et = param.annotation
            if et != inspect.Parameter.empty:
                try:
                    et(tool_input[name])
                except (ValueError, TypeError):
                    violations.append(f"参数 {name} 类型错误，期望 {et.__name__}")
        elif param.default == inspect.Parameter.empty:
            violations.append(f"缺少必填参数: {name}")
    return violations
```

### 5.5 L2 Mixin 拦截 - HallucinationGuardMixin

新文件 `src/qwenpaw/agents/hallucination_guard_mixin.py`：

辅助函数 `_extract_file_refs_from_cmd()` — 从 shell 命令中提取文件路径引用：

```python
import re

def _extract_file_refs_from_cmd(cmd: str) -> list[str]:
    """从 shell 命令中提取可能的文件路径引用。

    匹配：绝对路径 /path/to/file、相对路径 ./path、重定向 > file、--file=path
    """
    paths = []
    # 绝对/相对路径
    for m in re.finditer(r'(?:^|\s|["\'])((?:/|\.\.?/|[A-Za-z]:\\)[^\s"\']+)', cmd):
        paths.append(m.group(1).strip("'\""))
    # 重定向目标
    for m in re.finditer(r'[>]\s*([^\s;|&]+)', cmd):
        paths.append(m.group(1))
    # --flag=path 形式
    for m in re.finditer(r'--?\w+[=:](/[^\s"\']+|[A-Za-z]:\\[^\s"\']+)', cmd):
        paths.append(m.group(1))
    return [p for p in paths if len(p) > 3]
```

HallucinationGuardMixin 类：

```python
from pathlib import Path
from agentscope.message import Msg, ToolResultBlock


class HallucinationGuardMixin:
    """代码级幻觉防护 — 校验工具调用参数的真实性。

    MRO: QwenPawAgent -> HallucinationGuardMixin -> CodingModeMixin
         -> ToolGuardMixin -> ReActAgent
    """

    PATH_VALIDATION_TOOLS = frozenset({
        "read_file", "edit_file", "write_file",
        "grep_search", "view_image", "view_video",
    })
    QUERY_TOOLS = frozenset({
        "grep_search", "glob_search", "read_file",
    })

    async def _acting(self, tool_call):
        tool_name = str(tool_call.get("name", ""))
        tool_input = tool_call.get("input", {})

        # L2: 路径存在性校验 + 目录鉴别
        if tool_name in self.PATH_VALIDATION_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("path")
            if path:
                p = Path(path)
                if not p.exists():
                    await self._block(tool_call, "路径不存在")
                    return None
                if tool_name in ("read_file", "edit_file", "view_image", "view_video") and p.is_dir():
                    await self._block(tool_call, "是目录不是文件")
                    return None

        # L2: Shell 命令引用文件校验
        if tool_name == "execute_shell_command":
            for ref in _extract_file_refs_from_cmd(tool_input.get("command", "")):
                if not Path(ref).exists():
                    await self._block(tool_call, f"命令引用的文件不存在: {ref}")
                    return None

        # L1: Schema 校验
        fn = await self._get_tool_fn(tool_name)
        if fn:
            violations = _validate_tool_input(fn, tool_input)
            if violations:
                await self.memory.add(Msg(role="system", content="[修正引导] 请先查询再执行"))
                await self._block(tool_call, "; ".join(violations))
                return None

        # 执行工具（传递到 ToolGuardMixin — 返回值不可信，详见下）
        return await super()._acting(tool_call)

    async def _block(self, tool_call, reason):
        """阻断工具调用 — 将阻断消息写入 memory 后立即返回（不返回消息对象）。

        注意：_block 只负责将阻断消息写入 memory，不返回值。
        调用方应在 _block 后自行 return None。
        这与 ToolGuardMixin._acting_auto_denied() 的模式一致。
        """
        m = Msg(name="system", role="system", content=[ToolResultBlock(
            type="tool_result", id=tool_call.get("id", ""),
            name=tool_call.get("name", ""),
            output=[{"type": "text", "text": f"[幻觉防护] {reason}"}]),
        ])
        await self.memory.add(m)

    async def _get_tool_fn(self, name):
        tk = getattr(self, "toolkit", None)
        if not tk:
            return None
        for attr in ("tool_functions_map", "_tool_functions", "tools"):
            m = getattr(tk, attr, None)
            if isinstance(m, dict) and name in m:
                return m[name]
        return None
```

> **关于 L3 空结果声明**：`_acting()` 中无法可靠检测工具结果是否为空，
> 因为 `ToolGuardMixin._acting()` 在成功执行工具后返回 `None`（结果已写入 memory）。
> **L3 空结果声明应在 `post_acting` hook 中实现**（见 §6.3），
> 通过检查 memory 中最新一条 tool_result 的内容来决定是否追加防幻觉声明。

### 5.6 L3 空结果声明通用化

在 HallucinationGuardMixin._inject_empty_decl() 中已实现。

### 5.7 L4 Prompt 引导

在 AGENTS.md 入口点包含核心规则，仅作补充：
- 先查询再回答，不猜测编码值，写入必须预览

## 6. 护栏三：反馈循环 (Feedback Loop)

### 6.1 设计原则

拦截不够，还必须修正。不只说错了，还教正确做法。

### 6.2 幻觉拦截 + 修正引导

已在 5.5 节实现：拦截时返回阻断消息 + 将修正引导注入 memory。下一轮推理 LLM 看到修正引导后自动尝试正确做法。

修正引导质量：
- "参数校验失败" -> "文件不存在，请先用 glob_search 搜索正确路径"
- "操作被阻止" -> "请先预览(execute=False)确认后再执行"
- "无效 FormId" -> "请用 kingdee_search_form 查询"

### 6.3 Agent 自审机制

post_reply hook 实现（BaseContextManager 签名：`async def post_reply(self, agent, kwargs, output)`）：

```python
import re


def _extract_text_from_msg(msg) -> str:
    """从 Msg 对象中提取纯文本。"""
    if hasattr(msg, "content"):
        c = msg.content
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(
                b.get("text", "") for b in c
                if isinstance(b, dict) and b.get("type") == "text"
            )
    return str(msg)


def _contains_factual_claims(text: str) -> bool:
    """检测文本是否包含事实性声明（启发式）。"""
    patterns = [
        r'\d{4}-\d{2}-\d{2}',                    # 日期
        r'编码[是为:：]\s*\S+',                   # 编码值
        r'(?:金额|数量|总额|单价)为[：:]\s*[\d,.]+',  # 数字（用词组避免"量为"误报）
    ]
    return any(re.search(p, text) for p in patterns)


async def post_reply(self, agent, kwargs, output):
    """回复后：事实性声明自审。

    注意：post_reply hook 的 kwargs 包含用户输入，output 是 Agent 回复。
    自审必须检查 output，而非 kwargs.get("msg")（那是用户输入）。
    """
    msg = output  # output = Agent 的回复
    text = _extract_text_from_msg(msg)
    has_citation = bool(re.search(r'\[来源:', text))
    if _contains_factual_claims(text) and not has_citation:
        await agent.memory.add(Msg(
            role="system",
            content="【自审反馈】此回答含事实性声明但未标注来源，"
                    "请在后续回答中标注[来源:xxx]",
        ))
    return None
```

自审保护：最大循环 2 次（`MAX_SELF_REVIEW_CYCLES = 2`），置信度阈值 0.8，默认关闭。

### 6.4 引用溯源后处理

流程: 提取文本 -> 事实性检测 -> 引用标记检测 -> 无引用则注入反馈

### 6.5 反馈闭环

提问 -> pre_reply(记忆检索) -> _reasoning -> _acting(L2->L1->执行->L3) -> 修正引导(若拦截) -> _reasoning(修正) -> 循环 -> post_reply(自审)

## 7. 护栏四：熵管理 (Entropy Management)

### 7.1 设计原则

文档必须是活的反馈循环，静态文档是坟场。

### 7.2 Doc-gardening Agent

定时任务（每周）：

```python
# TODO: get_workspace_skills_dir, spawn_subagent 需从 agents/skill_system 和 tools 导入
# TODO: _api_still_exists 实现 API 存在性检查逻辑


class DocGardeningScheduler:
    """文档园丁 — 定期扫描技能文档与实际代码/API 之间的不一致。"""

    async def scan_skill_docs(self):
        for skill_dir in get_workspace_skills_dir():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            findings = []
            for api in self._extract_api_refs(skill_md.read_text(encoding="utf-8")):
                if not self._api_still_exists(api):
                    findings.append(f"API {api} 已不存在")
            if findings:
                await spawn_subagent(
                    task=f"文档腐烂: {findings}",
                    agent_id="doc-gardener",
                )

    def _extract_api_refs(self, content):
        return re.findall(r'`(\w+(?:\.\w+)*\([^)]*\))`', content)

    # TODO: 实现 _api_still_exists — 检查 API 是否仍存在于 toolkit 或 Python import 中
    def _api_still_exists(self, api_name: str) -> bool:
        return True  # 占位
```

### 7.3 Dream 增强

扩展 `prompts.py`：
- **事实性校验**：对编码值/API 端点等调用查询工具验证是否仍成立（TODO：需实现校验逻辑）
- **标记来源**：`[来源:查询]` / `[来源:推理]` / `[来源:用户]`

### 7.4 架构漂移扫描

```python
# TODO: DriftScanner 集成 ast-grep / pyright 等静态分析工具


class DriftScanner:
    """架构漂移扫描 — 后台 Agent 检测代码坏模式蔓延。"""

    async def scan(self):
        # TODO: 实现各模式的检测逻辑
        for p in ["hardcoded_secrets", "missing_error_handling"]:
            r = await self._detect(p)
            if r:
                print(f"漂移: {p} x {len(r)}")

    async def _detect(self, pattern: str):
        return []  # 占位
```

### 7.5 持续小额偿还

> **原则**：技术债务就像高息贷款，持续小额偿还比集中处理更好。

实践中，Doc-gardening（§7.2）、Dream 增强（§7.3）和架构漂移扫描（§7.4）
构成了「发现→修正→验证」的持续改进闭环。三者协同工作：

1. **发现**：DriftScanner 定期检测代码坏模式
2. **修正**：Doc-gardening Agent 提交修正 PR
3. **验证**：Dream 增强确保记忆不包含过时事实
```

## 8. 实施路线图

第一阶段 (1-2天) P0 硬性约束层:
| 任务 | 文件 | 工时 |
|------|------|------|
| 创建 HallucinationGuardMixin | agents/hallucination_guard_mixin.py (新) | 4h |
| 修改 MRO 继承链 | agents/react_agent.py | 0.5h |
| L1 Schema 校验集成 | hallucination_guard_mixin.py | 1h |
| 路径存在性校验 | hallucination_guard_mixin.py | 1h |
| L3 空结果声明 | hallucination_guard_mixin.py | 1h |
| 集成测试 | tests/ | 2h |

第二阶段 (1天) P1 上下文+反馈:
| 任务 | 文件 | 工时 |
|------|------|------|
| PromptBuilder 两阶段构建 | agents/prompt.py | 3h |
| post_reply 自审+引用检测 | context/light_context_manager.py | 2h |
| 引用溯源规则注入 | agents/prompt.py | 1h |

第三阶段 (可选) P2 熵管理:
| 任务 | 文件 | 工时 |
|------|------|------|
| Doc-gardening | app/crons/doc_gardening.py (新) | 3h |
| Dream 增强 | agents/memory/prompts.py | 1h |

## 9. 金蝶 ERP 插件改造路径

### 9.1 现状

| 函数 | 职责 | 位置 |
|------|------|------|
| _is_valid_form_id() | FormId 白名单 | tools.py:~1014 |
| _preview_key() / _check_previewed() | 防跳步指纹 | tools.py:~941 |
| _build_block_response() | 阻断响应 | tools.py:~964 |

### 9.2 改造路径

短期: 保持现状，各自独立运行
中期: 金蝶插件继承 AntiHallucinationToolMixin，迁移到 PARAM_WHITELISTS
长期: 新插件声明类变量即自动获防护

## 10. 验收标准

功能验收(可自动化):
| 验收项 | 测试方法 | 通过标准 |
|--------|----------|----------|
| L2 路径校验 | tool_call(read_file, /nonexist) | 阻断含"路径不存在" |
| L2 目录检测 | tool_call(read_file, .) | 阻断含"是目录" |
| L1 Schema | tool_call(edit_file, file_path=123) | 类型错误提示 |
| L1 必填参数 | tool_call(read_file, {}) | 缺少必填参数 |
| L0 双步调用 | execute=True 未预览 | 请先预览 |
| L3 空结果声明 | 查询返回空 | 含空结果声明 |
| 引用溯源 | 事实性回答无[来源:xxx] | post_reply 注入反馈 |
| 反馈循环 | 拦截后检查 memory | 含修正引导 |

性能验收:
| 验收项 | 标准 |
|--------|------|
| L2 路径校验 p99 | < 5ms |
| L1 Schema 校验 p99 | < 1ms |
| 系统提示词缩减 | < 改造前 60% |
| 误拦截率 | 0% |

## 11. 风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| HallucinationGuardMixin 与 ToolGuardMixin MRO 冲突（HGM/TGM） | 高 | 低 | 每个 _acting 调 super(); 测试覆盖 |
| Schema 误拦截 | 中 | 中 | 宽松类型转换; 可配置跳过 |
| agentscope API 变更 | 高 | 中 | 适配器; 单元测试 |
| 入口点规则遗漏 | 中 | 中 | L0-L2 硬性兜底 |
| 反馈循环 token 增加 | 中 | 中 | 修正引导 < 200 token; 自审默认关 |

监控: HGM 拦截日增长>50%, Schema 失败率>5%, 系统提示词增长>10% 触发告警
