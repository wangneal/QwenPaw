# 金蝶 ERP Agent 聊天与权限接口 UAT 报告

测试日期：2026-06-07

## 测试方式

本轮测试使用 HTTP API 黑盒调用，不使用浏览器点击 WebUI。

- 服务地址：`http://127.0.0.1:8089`
- 聊天接口：`POST /api/console/chat`
- Agent 注册接口：`GET /api/agents`
- 工具注册接口：`GET /api/agents/{agent_id}/tools`
- 权限接口：`/api/erp-permissions/*`
- 结果文件：`docs/uat_erp_chat_permissions_results.json`
- UAT 脚本：`scripts/uat_erp_chat_permissions.py`

## 最新复测结论

复测时间：2026-06-07 20:35:37

模型切换并传播到 ERP 专家 Agent 后，完整接口 UAT 已通过。

- 当前模型：`local/deepseek-v4-flash-free`
- 完整 UAT：`25/25`
- 失败数：`0`
- 通过率：`100.0%`
- 耗时：`285.2s`
- 结果文件：`docs/uat_erp_chat_permissions_results.json`

本轮复测未再出现 `MODEL_QUOTA_EXCEEDED`，抽查未发现 `The user`、`用户想` 等硬性内部推理泄露标记。

## 历史阻断结论

模型切换前不能判定为完整生产通过，原因如下。

已通过项：

- ERP Agent 注册通过：`default`、`erp-finance`、`erp-sales`、`erp-purchase`、`erp-inventory`、`erp-executive` 均已注册。
- ERP 工具注册通过：企业版工具已启用，旗舰版工具默认不启用。
- 权限 API 通过：权限创建、查询、操作权限查询、默认组织按 Agent 隔离、未授权组织拒绝均通过。
- 插件业务单测通过：`plugins/tool/kingdee-erp/tests/test_kingdee_business_tools.py` 为 `29 passed`。

历史阻断项：

- 最新聊天 UAT 为 `12/25`。
- 13 个聊天用例均被模型侧 `MODEL_QUOTA_EXCEEDED: nemotron-3-ultra-free` 阻断。
- 该失败发生在 `/api/console/chat` 调用阶段，属于当前本地模型额度/限流问题，不是权限接口或 ERP 插件工具注册失败。

## 已修复问题

- UAT 判定已加严：中文内部推理、空格压缩英文推理、裸异常、模型错误均作为失败项。
- 增加 console 公共输出守卫：用于过滤 `/api/console/chat` 中用户可见的内部推理文本；可通过 `QWENPAW_CONSOLE_PUBLIC_OUTPUT_GUARD=0` 关闭。
- ERP Agent 运行期提示词前置：只允许输出最终答复、操作摘要、阻断原因、下一步动作和必要确认问题。
- 新增分组编码查询闭环工具：`kingdee_query_group_by_business_key`，用于按分组编码、名称或内码查询基础资料分组，内部解析后调用 `QueryGroupInfo`。

## 待复测

模型恢复或切换可用模型后，需要重新执行：

```powershell
python scripts\uat_erp_chat_permissions.py --base-url http://127.0.0.1:8089 --timeout 240 --output docs\uat_erp_chat_permissions_results.json
```

通过标准：

- `25/25` 通过。
- 聊天响应不得出现 `用户想`、`我需要`、`让我`、`The user wants`、`I need`、`Let me` 等内部推理文本。
- 写入类场景必须先返回预览，不得静默执行。
- 分组新增、查询、删除，客户分配、取消分配，供应商新增后撤销均需形成业务闭环。
