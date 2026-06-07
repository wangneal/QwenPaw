# 项目开发规则

本文件是本仓库的开发约束。修改代码、提示词、插件清单、内置 Agent 配置或测试时必须遵守。

## 金蝶 ERP 插件边界

- 当前金蝶 ERP 插件按金蝶云星空企业版实现。不得把企业版接口改成旗舰版接口，也不得优先引用 `kingdee_flagship` 目录中的实现。
- 不得修改内置 QA 模板，包括 `src/qwenpaw/agents/md_files/qa/**` 下的 `SOUL.md`、`PROFILE.md`、`AGENTS.md` 等文件，除非需求明确要求修改 QA 模板。
- 金蝶 ERP 插件相关变更应优先限制在 `plugins/tool/kingdee-erp/**` 及其前端管理页面范围内；跨到核心 QwenPaw 代码前必须确认确实是平台能力缺口。

## 提示词和工具描述

- 金蝶工具描述、Agent 报表摘要模板、运行时提示语必须统一管理。新增或修改工具描述时优先维护 `plugins/tool/kingdee-erp/backends/kingdee/prompts.py`。
- `backend.py` 注册工具不得重新内联工具描述。必须从 `TOOL_DEFINITIONS` 读取。
- `erp_report_digest.py` 不得重新定义报表模板。必须从 `REPORT_TEMPLATES` 读取。
- `plugin.json` 的 `meta.tools` 必须与 `prompts.build_manifest_tools()` 输出一致；更新工具清单时必须同步测试。
- 提示词、工具描述和用户可见工程提示必须使用中文，采用工程化指令表达，避免口语化措辞。
- 禁止在提示词、工具描述、插件清单、运行时提示和内置文档中使用 emoji、表情符号或装饰性图标。
- ERP 专业 Agent 默认技能不得挂载口语化润色类技能；输出必须面向业务结论，不得暴露内部思考、工具选择推理或执行计划草稿。
- 写入预览、拦截提示、空结果提示和业务失败提示必须明确说明执行条件、阻断原因和下一步动作，不能用泛泛的提示语替代工具层约束。

## 业务闭环要求

- 增删改查必须形成工具层闭环，不能依赖 LLM 记忆、猜测或自由补全业务对象。
- 新增后再撤销的场景必须通过工具层最近实体记录或明确查询结果定位目标；不能让 LLM 猜单号、内码或组织。
- 所有写入、删除、提交、审核、反审核、下推、分配、取消分配和自定义操作必须保留 `execute=False` 预览到 `execute=True` 执行的双步确认。
- Kingdee `ResponseStatus.IsSuccess=false` 或返回错误明细时，工具必须按业务失败处理，不能只按 HTTP 成功判断成功。
- 查询类工具遇到业务失败返回也必须显式失败；空结果必须声明没有匹配数据，不能生成推测性结果。
- 基础资料分组、分配、取消分配等企业版接口必须支持不同 `FormId`，不能硬编码只服务客户，除非工具名明确限定客户业务封装。

## 组织上下文和权限

- 默认组织必须按 `agent/channel/user` 维度管理。多个用户、多个渠道或多个智能体不能共享一个默认组织。
- 用户首次使用未配置默认组织时，应引导其设置默认组织；后续未明确切换组织时使用该默认组织。
- WebUI 访问金蝶权限拦截可配置关闭，但默认逻辑不能绕过金蝶权限配置。任何 bypass 都必须有明确配置项和测试覆盖。
- 权限检查、行级过滤、字段级过滤和审计日志属于生产级能力，不得为了让流程跑通而跳过。

## 测试和校验

- 修改金蝶 ERP 后端能力后，至少运行：
  - `python -m py_compile plugins\tool\kingdee-erp\backends\kingdee\tools.py plugins\tool\kingdee-erp\backends\kingdee\backend.py plugins\tool\kingdee-erp\backends\kingdee\erp_report_digest.py plugins\tool\kingdee-erp\backends\kingdee\prompts.py plugins\tool\kingdee-erp\erp_permissions.py`
  - `python -m pytest plugins\tool\kingdee-erp\tests\test_kingdee_business_tools.py plugins\tool\kingdee-erp\tests\test_permissions.py`
- 修改工具描述、报表模板或 `plugin.json` 时，必须保证 `test_manifest_tools_match_centralized_prompt_definitions` 和无 emoji 检查通过。
- 不得删除或弱化业务闭环测试来规避失败。测试失败时应修复实现或明确说明阻塞原因。
