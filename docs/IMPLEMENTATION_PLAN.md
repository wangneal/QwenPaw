# QwenPaw 幻觉驾驭层实现计划

> **基准文档**: `docs/HALLUCINATION_HARNESS_DESIGN.md`
> **实现版本**: 1.0.0
> **估算总工时**: 17-21h

---

## 阶段划分

| 阶段 | 内容 | 工时 | 依赖 |
|------|------|------|------|
| **P1** | HallucinationGuardMixin 核心 + L0 基类 | 7h | 无 |
| **P2** | MRO 集成 + 上下文工程 | 4h | P1 |
| **P3** | 反馈循环 Hook | 4h | P1 |
| **P4** | 熵管理定时任务 | 3h | 无（可选） |
| **P5** | 测试 + 验证 | 3h | P1-P3 |

---

## P1: HallucinationGuardMixin 核心 + L0 基类（7h）

### P1.1 创建辅助函数（1h）

**文件**: `src/qwenpaw/agents/hallucination_guard_mixin.py`（新建）

```
P1.1.1 _extract_file_refs_from_cmd()
  - 实现正则：绝对路径、相对路径、重定向、--flag=path
  - 单元测试：覆盖 Windows、Linux、UNIX 路径

P1.1.2 _validate_tool_input()
  - 使用 inspect.signature 自动推导函数签名
  - 类型转换宽松校验（int("5") 通过，int("abc") 失败）
  - 必填参数缺失检测
  - 单元测试：覆盖正常/异常/边界参数
```

### P1.2 创建 HallucinationGuardMixin 类（3h）

**文件**: `src/qwenpaw/agents/hallucination_guard_mixin.py`

```
P1.2.1 类声明 + 常量
  - class HallucinationGuardMixin
  - PATH_VALIDATION_TOOLS: frozenset
  - QUERY_TOOLS: frozenset

P1.2.2 _acting() 方法
  - L2 文件路径存在性校验 + 目录鉴别
  - L2 Shell 命令引用文件校验
  - L1 Schema 类型校验
  - MCP 工具：_get_tool_fn() 返回 None 时跳过 Schema 校验，仅做路径校验
  - write_file：父目录存在时放行（新建文件场景），仅拦截父目录也不存在的路径
  - 调用 super()._acting() 传递到 ToolGuardMixin
  - 并发安全：无共享状态，免锁

P1.2.3 _block() 方法
  - 构造 ToolResultBlock 格式的阻断消息
  - memory.add() 写入记忆
  - 不返回值（return None）

P1.2.4 _get_tool_fn() 适配器
  - 兼容 agentscope Toolkit 的多种 API 命名
  - tool_functions_map -> _tool_functions -> tools 轮询

P1.2.5 _build_correction_hint()
  - 按工具名分派修正引导消息
  - 语言：中文
```

### P1.3 空结果声明 Hook（1h）

**文件**: `src/qwenpaw/agents/context/light_context_manager.py`

```
P1.3.1 post_acting hook 中实现空结果检测
  - 检查 memory 中最新 tool_result 的文本长度
  - 文本长度 < 5 时追加空结果声明
  - 声明文本：硬编码"查询返回空结果，不要编造替代答案"

P1.3.2 注册 hook
  - hook_type="post_acting", hook_name="empty_declaration_hook"
  - 注册位置：react_agent.py _register_hooks()
```

### P1.5 AntiHallucinationToolMixin — L0 基类（1h）

**文件**: `src/qwenpaw/agents/tools/base.py`（新建）

```
P1.5.1 AntiHallucinationToolMixin 类
  - PARAM_WHITELISTS: dict[str, set[str]] 类变量
  - REQUIRES_PREVIEW: bool 类变量
  - DECLARE_EMPTY_RESULT: bool 类变量
  - __init__ 中创建 asyncio.Lock + _previewed_keys 集合

P1.5.2 enforce_two_step()
  - execute=False 时生成预览指纹并注册
  - execute=True 时检查指纹是否已注册
  - 指纹：MD5(params) 前 16 位
  - 并发安全：asyncio.Lock 保护

P1.5.3 validate_param_against_whitelist()
  - 按 PARAM_WHITELISTS 校验参数值合法性
  - 非法值返回错误消息

P1.5.4 declare_if_empty()
  - 结果为空时返回防幻觉声明文本
```

> **边缘情况处理**：
> - `write_file` 创建新文件：路径校验仅拦截绝对不存在的路径。`write_file` 要写入的路径父目录存在时放行（父目录存在意味着路径有效，文件可能被新建）
> - MCP 工具：`_get_tool_fn()` 对 MCP 工具返回 `None`，跳过 Schema 校验（L1），仅保留 L2 路径校验。参见设计文档 §12 C1

**文件**: `src/qwenpaw/agents/context/light_context_manager.py`

```
P1.4.1 _extract_text_from_msg()
  - 提取 Msg.content 中的纯文本
  - 支持 TextBlock 列表格式 + 纯文本格式

P1.4.2 _contains_factual_claims()
  - 正则匹配事实性声明
  - 日期 / 编码值 / 金额数量 / 专有名词

P1.4.3 post_reply 自审
  - 使用 output 参数（而非 kwargs.get("msg")）
  - 检测事实性声明 + 引用标记
  - 无引用时注入自审反馈到 memory
  - 默认关闭（enable_self_review=False）
```

---

## P2: MRO 集成 + 上下文工程（4h）

### P2.1 修改 MRO 继承链（0.5h）

**文件**: `src/qwenpaw/agents/react_agent.py`

```python
# 从第 83 行修改
class QwenPawAgent(
    HallucinationGuardMixin,  # [NEW] 最优先
    CodingModeMixin,
    ToolGuardMixin,
    ReActAgent,
):
```

### P2.2 注册新 Hook（0.5h）

**文件**: `src/qwenpaw/agents/react_agent.py`

```
- 在 _register_hooks() 中注册：
  - hallucination_post_acting -> empty_declaration_hook
  - hallucination_post_reply -> self_review_hook（条件注册）
```

### P2.3 PromptBuilder 两阶段构建（2h）

**文件**: `src/qwenpaw/agents/prompt.py`

```
P2.3.1 阶段1：核心入口点（始终注入）
  - SOUL.md 全量（身份定义不宜拆分）
  - PROFILE.md 全量（通常简短）
  - AGENTS.md 摘要（提取 < 800 token 的核心规则）
  - 工具列表（仅名称 + 一句话描述）

P2.3.2 阶段2：按需注入
  - pre_reasoning hook 中检测活跃技能
  - 只注入触发技能的 SKILL.md
  - 记录已注入技能避免重复

P2.3.3 配置开关（向后兼容）
  - agents.system_prompt_mode: "compact" | "full"
  - 默认为 "compact"
  - "full" 保留现有全量注入行为
```

### P2.4 引用溯源规则注入（1h）

**文件**: `src/qwenpaw/agents/prompt.py`

```
- CITATION_RULE 注入到阶段1的入口点末尾
- 引用规则文本：标注 [来源:xxx]
- 配合 P1.4.3 的 post_reply 自审
```

---

## P3: 反馈循环 Hook（4h）

### P3.1 pre_reply 增强（1h）

**文件**: `src/qwenpaw/agents/context/light_context_manager.py`

```
- 提取 msg 主题（_extract_topics，先用简单关键词匹配）
- 按主题相关性检索记忆（top_k=5）
- 注入 CONFLICT_DETECTION_INSTRUCTION
- 冲突检测说明：标注为 L4 辅助层，不依赖
```

### P3.2 pre_reasoning 增强（1h）

**文件**: `src/qwenpaw/agents/context/light_context_manager.py`

```
- _detect_active_skills() 基础实现
  - 从 msg 文本中匹配技能名称关键词
  - 匹配规则：skills 目录下的文件名
- 未加载过的技能注入对应 SKILL.md
- 记录已加载技能集合
```

### P3.3 知识冲突代码级检测（2h）

**文件**: `src/qwenpaw/agents/context/light_context_manager.py`

```
- 在 post_reply 中实现：
  - 获取当前回复文本
  - 获取最近注入的记忆片段（pre_reply 时缓存）
  - 简易冲突检测：
    - LLM 回复中的值 vs 记忆中的值是否矛盾
    - 矛盾时追加修正声明
- 注意：此检测是启发式的，误报可配置阈值
```

---

## P4: 熵管理定时任务（3h，可选）

### P4.1 Doc-gardening Agent（1.5h）

**文件**: `src/qwenpaw/app/crons/doc_gardening.py`（新建）

```
- APScheduler 定时任务（每周一次）
- _extract_api_refs: 从 SKILL.md 提取 API 引用
- _api_still_exists: 检查 API 是否仍在 toolkit 中
- 发现腐烂时提交 spawn_subagent 修正任务
- 初始实现：仅记录日志，不自动修正
```

### P4.2 Dream 增强（1h）

**文件**: `src/qwenpaw/agents/memory/prompts.py`

```
- 修改 DREAM_OPTIMIZATION_ZH
- 增加原则5：事实性校验
- 增加原则6：幻觉溯源标记
```

### P4.3 架构漂移扫描（0.5h）

**文件**: `src/qwenpaw/app/crons/drift_scanner.py`（新建）

```
- 定时任务（每月一次）
- 当前为占位，仅记录扫描进度日志
- 后续集成 ast-grep 或 pyright
```

---

## P5: 测试 + 验证（3h）

### P5.1 单元测试（1.5h）

```
文件: tests/test_hallucination_guard.py

- test_block_path_not_exist: read_file("/nonexistent") => 阻断
- test_block_path_is_dir: read_file(".") => 阻断（是目录）
- test_allow_valid_path: read_file(有效的已存在文件) => 放行
- test_block_schema_type_error: edit_file(file_path=123) => 类型错误
- test_block_missing_required_param: read_file({}) => 缺少必填参数
- test_two_step_execute_without_preview: execute=True 未预览 => 拒绝
- test_empty_result_declaration: 查询返回空 => 含声明文本
- test_extract_file_refs: shell 命令中提取路径
- test_validate_tool_input: 正常/异常/边界参数
- test_contains_factual_claims: 日期/编码/金额/非事实文本
- test_extract_text_from_msg: 多种 Msg 格式
```

### P5.2 集成测试（1h）

```
- test_mro_chain: HallucinationGuardMixin -> ToolGuardMixin 链路
- test_hook_registration: post_acting/post_reply 正确注册
- test_prompt_builder_compact: 入口点模式 token < 改造前 60%
- test_kingdee_compatibility: 金蝶插件不受影响
```

### P5.3 性能基线（0.5h）

```
- benchmark_path_validation_p99: p99 < 5ms
- benchmark_schema_validation_p99: p99 < 1ms
- benchmark_false_positive_rate: 0%（对现有有效路径）
```

---

## 依赖图

```
P1.1 辅助函数
  |
  v
P1.2 HallucinationGuardMixin ---> P1.3 空结果 Hook
  |                                 |
  v                                 v
P2.1 MRO 集成                   P1.4 自审函数
  |                                 |
  v                                 v
P2.2 注册 Hook                  P3.1 pre_reply 增强
  |                                 |
  v                                 v
P2.3 PromptBuilder               P3.2 pre_reasoning 增强
  |                                 |
  v                                 v
P2.4 引用溯源                    P3.3 冲突检测
  |
  v
P5 测试 + 验证
```

---

## 风险点

| 风险 | 缓解 |
|------|------|
| agentscope Toolkit API 命名不确定 | _get_tool_fn 使用适配器轮询多种属性名 |
| InMemoryMemory.search() API 参数不确定 | 实现阶段验证，必要时降级为全部返回 |
| _detect_active_skills 准确度低 | 先用关键词匹配，后续升级为 LLM 分类 |
| MRO 变更影响 CodingModeMixin | CodingModeMixin 不覆盖 _acting，无影响 |
