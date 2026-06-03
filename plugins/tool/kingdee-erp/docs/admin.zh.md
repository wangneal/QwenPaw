# 星智 管理员指南

本文档面向系统管理员，涵盖部署、配置、权限管理和运维操作。

---

## 部署

### 系统要求

- Docker 20.10+
- 金蝶云星空 WebAPI 可访问（需确认网络连通性）
- LLM 模型 API Key（推荐通义千问或 DeepSeek）

### Docker 部署

构建并启动容器：

```bash
# 构建白标镜像
docker build -t kingdee-erp-assistant:latest .

# 启动服务
docker run -d \
  --name kd-erp \
  -p 8088:8088 \
  -v kd-erp-data:/app/working \
  -v kd-erp-secrets:/app/working.secret \
  -v kd-erp-backups:/app/working.backups \
  kingdee-erp-assistant:latest
```

首次启动后，访问 `http://<服务器IP>:8088` 进入控制台。

### 端口与存储

暴露端口：

| 端口 | 用途 |
|------|------|
| 8088 | Web 控制台 + API |

Docker Volume：

| Volume 名称 | 容器路径 | 用途 |
|-------------|----------|------|
| kd-erp-data | /app/working | Agent 工作区、插件数据、权限数据库 |
| kd-erp-secrets | /app/working.secret | LLM API Key 等敏感配置 |
| kd-erp-backups | /app/working.backups | 自动备份 |

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| QWENPAW_HOST | 监听地址 | 0.0.0.0 |
| QWENPAW_PORT | 监听端口 | 8088 |
| QWENPAW_LOG_LEVEL | 日志级别 | INFO |

---

## 金蝶连接配置

### 在控制台配置

进入 **控制台 → 插件 → 找到"可扩展ERP工具插件" → 连接配置**，填写以下参数：

| 配置项 | 必填 | 说明 |
|--------|------|------|
| 金蝶服务器地址 | 是 | WebAPI 地址，格式 `http://<IP>/k3cloud/`，必须以 `/k3cloud/` 结尾 |
| 账套ID | 是 | 金蝶账套标识，如 `6304ba61219bf5` |
| 用户名 | 是 | 金蝶登录用户名 |
| 应用ID | 是 | 第三方应用授权的 App ID，格式如 `225649_xxxxx` |
| 应用密钥 | 是 | 第三方应用授权的 App Secret（密码类型，控制台显示掩码） |
| 管理员联系方式 | 否 | 权限提示中展示，方便用户联系管理员，如 `admin@company.com` |
| 金蝶云社区 Token | 否 | 产品智能问答功能需要，格式如 `kdt_xxxxxxxx...` |
| 金蝶产品 | 否 | 产品问答的目标产品，默认"金蝶AI星空企业版" |

### 获取金蝶应用授权

1. 登录金蝶云星空管理后台
2. 进入 **基础管理 → 第三方应用**
3. 创建应用，获取 App ID 和 App Secret
4. 为应用分配所需权限（查询、写入等）
5. 将 App ID 和 App Secret 填入插件配置

### 获取金蝶云社区 Token（产品问答功能）

1. 访问金蝶云社区并登录
2. 进入 **个人主页 → 编辑资料 → 个人访问令牌**
3. 创建 Token，复制填入配置

### 验证连接

配置完成后，在控制台聊天中输入："查询一下有哪些组织"。如果返回组织列表，说明连接成功。

---

## 模型配置

星智使用云端大语言模型，不支持本地模型部署。

### 添加模型 Provider

进入 **控制台 → 模型管理**，添加以下 Provider：

**通义千问（推荐）**

| 配置项 | 值 |
|--------|-----|
| Provider ID | dashscope |
| API Key | 从 DashScope 控制台获取 |
| Base URL | https://dashscope.aliyuncs.com/compatible-mode/v1 |

**DeepSeek**

| 配置项 | 值 |
|--------|-----|
| Provider ID | deepseek |
| API Key | 从 DeepSeek 平台获取 |
| Base URL | https://api.deepseek.com |

### 推荐模型

| 用途 | 推荐模型 | 说明 |
|------|----------|------|
| 日常对话 | Qwen-Max / DeepSeek-V3 | 性价比高，响应快 |
| 复杂报表分析 | Qwen-Max / GPT-4o | 推理能力强 |
| 产品问答 | Qwen-Plus | 响应快，知识面广 |

### 为 Agent 配置模型

初始化脚本会自动将默认 Agent 的模型配置传播到所有专业 Agent。如需单独调整某个 Agent 的模型，在控制台进入该 Agent 的设置页面修改。

---

## Agent 初始化

### 运行初始化脚本

Docker 镜像已内置初始化脚本。首次部署后需执行：

```bash
# 复制初始化脚本到容器
docker cp scripts/setup_erp_agents.py kd-erp:/tmp/

# 执行初始化（创建 5 个专业 Agent + 配置路由）
docker exec kd-erp python3 /tmp/setup_erp_agents.py

# 重启使配置生效
docker restart kd-erp
```

初始化脚本会完成以下工作：

1. 创建 5 个专业 Agent（财务、销售、库存、采购、高管决策）
2. 复制角色定义文件（SOUL.md + PROFILE.md）到每个 Agent
3. 安装 ERP 技能文件并注册到 skill.json
4. 启用金蝶工具到每个 Agent 的 agent.json
5. 将默认 Agent 的模型和金蝶连接配置传播到专业 Agent
6. 在默认 Agent 的 SOUL.md 中添加 ERP 语义路由规则
7. 插入默认管理员权限（Console 聊天可直接测试）
8. 迁移配置到自管 JSON 文件

### Agent 列表

初始化后会创建以下 Agent：

| Agent ID | 名称 | 职责 | 金蝶业务域 | 预装技能 |
|----------|------|------|-----------|----------|
| erp-finance | 财务助手 | 会计科目、凭证、报表 | GL_, AR_, AP_ | 查询指南、字段映射、写入安全、财务字段、产品问答 |
| erp-sales | 销售助手 | 订单、客户、报价 | SAL_ | 查询指南、字段映射、写入安全、销售字段、产品问答 |
| erp-purchase | 采购助手 | 采购单、供应商 | PUR_ | 查询指南、字段映射、写入安全、采购字段、产品问答 |
| erp-inventory | 库存助手 | 出入库、盘点 | STK_ | 查询指南、字段映射、写入安全、库存字段、产品问答 |
| erp-executive | 高管决策助手 | 跨域汇总、经营分析 | 全域 | 查询指南、字段映射、跨系统对账/关联/月结/下推、报表摘要、产品问答 |

### 语义路由

默认 Agent 充当路由器。路由规则已由初始化脚本写入默认 Agent 的 SOUL.md：

| 关键词 | 路由目标 |
|--------|----------|
| 凭证、科目、总账、应收、应付、财务、报表 | erp-finance |
| 销售订单、客户、报价、出库 | erp-sales |
| 采购、供应商、入库、比价 | erp-purchase |
| 库存、盘点、出入库、仓库 | erp-inventory |
| 经营分析、汇总、对账、决策 | erp-executive |
| ERP 相关但不确定 | erp-finance（默认） |
| 非 ERP 问题 | 默认 Agent 直接回答 |

如需修改路由规则，编辑 `/app/working/workspaces/default/SOUL.md` 中的"ERP 语义路由"部分。

---

## 权限管理

### 权限模型

权限采用 **用户 × 组织 × 业务域 × 访问级别** 四维模型：

| 维度 | 说明 | 示例值 |
|------|------|--------|
| 用户标识 | 渠道:用户ID | wecom:zhangsan |
| 组织 | 金蝶组织编号 | 01, 02, *（全部） |
| 业务域 | 数据范围 | finance, sales, inventory, procurement, production, hr, base |
| 访问级别 | 只读/读写 | readonly, writeable |

业务域与金蝶表单前缀的对应关系：

| 业务域 | 说明 | 包含表单前缀 |
|--------|------|-------------|
| finance | 财务 | GL_, AR_, AP_ |
| sales | 销售 | SAL_ |
| procurement | 采购 | PUR_ |
| inventory | 库存 | STK_ |
| production | 生产 | PRD_ |
| hr | 人事 | HR_, BD_Employee |
| base | 基础资料 | BD_ |

### 通过管理界面管理权限

安装 erp-admin 前端插件后，在控制台会出现权限管理入口。

操作步骤：
1. 进入 **插件 → 金蝶云星空权限管理**
2. 点击 **添加权限**
3. 填写用户标识（如 `wecom:zhangsan`）
4. 选择组织（输入组织编号或 `*` 表示全部）
5. 勾选允许访问的业务域
6. 选择访问级别（只读 / 读写）
7. 保存

### 通过 API 管理权限

权限管理接口：`/api/erp-permissions`

```bash
# 查询所有权限
curl http://localhost:8088/api/erp-permissions

# 查询指定用户权限
curl http://localhost:8088/api/erp-permissions?key=wecom:zhangsan

# 添加/更新权限
curl -X POST http://localhost:8088/api/erp-permissions \
  -H "Content-Type: application/json" \
  -d '{
    "key": "wecom:zhangsan",
    "display_name": "张三",
    "org_id": "*",
    "domains": ["finance", "sales"],
    "access": "readonly"
  }'

# 删除指定用户+组织的权限
curl -X DELETE http://localhost:8088/api/erp-permissions \
  -H "Content-Type: application/json" \
  -d '{"key": "wecom:zhangsan", "org_id": "*"}'

# 删除用户的所有权限
curl -X DELETE http://localhost:8088/api/erp-permissions \
  -H "Content-Type: application/json" \
  -d '{"key": "wecom:zhangsan"}'
```

### 渠道用户身份映射

不同渠道的用户身份格式：

| 渠道 | 用户标识格式 | 示例 |
|------|-------------|------|
| 控制台 | console:<user_id> | console:default |
| 钉钉 | dingtalk:<userid> | dingtalk:012345 |
| 飞书 | lark:<open_id> | lark:ou_xxxx |
| 微信 | wechat:<openid> | wechat:oXXXX |
| API | api:<custom_id> | api:erp-user-01 |

### 默认权限

初始化脚本会自动插入以下默认权限：

| 用户标识 | 组织 | 权限 | 说明 |
|----------|------|------|------|
| console:default | *（全部） | 全域读写 | Console 聊天身份，方便测试 |
| unknown:unknown | *（全部） | 全域读写 | 开发调试身份 |

**生产环境安全要求：务必删除 `unknown:unknown` 的权限条目。**

删除命令：
```bash
curl -X DELETE http://localhost:8088/api/erp-permissions \
  -H "Content-Type: application/json" \
  -d '{"key": "unknown:unknown", "org_id": "*"}'
```

### 权限数据库

权限存储位置：`/app/working/plugin_data/erp/permissions.db`（SQLite）

备份命令：
```bash
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db ".dump" > permissions_backup.sql
```

---

## 频道配置

### 钉钉

1. 登录钉钉开放平台，创建企业内部机器人
2. 获取机器人的 AppKey 和 AppSecret
3. 在控制台 **频道管理** 中添加钉钉频道，填入凭证
4. 配置消息接收地址为 `http://<服务器IP>:8088/api/channel/dingtalk/callback`
5. 在钉钉中将机器人添加到目标群组

### 飞书

1. 登录飞书开放平台，创建企业自建应用
2. 启用机器人能力，获取 App ID 和 App Secret
3. 在控制台 **频道管理** 中添加飞书频道，填入凭证
4. 配置事件订阅地址为 `http://<服务器IP>:8088/api/channel/lark/callback`
5. 发布应用并授权给目标用户

### 微信

1. 登录微信公众平台，获取 AppID 和 AppSecret
2. 在控制台 **频道管理** 中添加微信频道
3. 配置服务器地址和 Token

### 控制台

控制台默认可用，无需额外配置。用户直接在浏览器中访问系统地址即可使用。

---

## 安全配置

### 写入操作防护

所有写入类工具（保存、删除、提交、审核、反审核、下推、自定义操作、工作流审批）内置三重防护：

**第一重：双步调用**
- 第一次调用 execute=False（默认）：仅返回操作预览
- 用户确认后第二次调用 execute=True：执行实际操作

**第二重：FormId 白名单校验**
- 系统从元数据文件加载所有合法的 FormId
- 不在白名单中的 FormId 会被拒绝，防止模型编造表单

**第三重：防跳步机制**
- 系统记录每次预览的操作指纹
- 执行时校验是否已预览过相同操作
- 禁止跳过确认直接传 execute=True

### 审计日志

所有写入操作自动记录到审计日志，包含操作人、操作类型、表单、目标、详情和时间。

查看最近操作：
```bash
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db \
  "SELECT datetime(created_at, 'localtime') as time, operator, action, form_id, target
   FROM audit_log ORDER BY created_at DESC LIMIT 20"
```

审计日志字段说明：

| 字段 | 说明 |
|------|------|
| request_id | 请求追踪 ID |
| operator | 操作者用户标识（渠道:用户ID） |
| action | 操作类型（save/delete/submit/audit/unaudit/push/execute_op/workflow_audit） |
| form_id | 金蝶表单 ID |
| target | 操作目标（单据编号等） |
| detail | 操作详情 |
| created_at | 操作时间 |

审计日志超过 10000 条时自动归档到 `/app/working/plugin_data/erp/audit_archive/` 目录（Excel 或 CSV 格式）。

### 数据隔离

- 不同组织的数据通过 org_id 过滤，用户只能查询有权限的组织数据
- 不同业务域的数据通过 domains 过滤，用户只能访问被授权的域
- 金蝶 WebAPI 通过登录上下文做组织隔离

### 敏感信息保护

| 数据 | 存储位置 | 保护措施 |
|------|----------|----------|
| 金蝶 App Secret | 插件配置 | 密码类型字段，控制台显示掩码 |
| LLM API Key | /app/working.secret/ | Docker 独立 Volume |
| 用户权限 | SQLite 数据库 | Docker Volume 持久化 |
| 审计日志 | 同权限数据库 | 自动归档，保留最近 10000 条 |

---

## 定时任务

### 通过 CLI 创建定时报表

```bash
# 创建销售日报（每天 09:00）
docker exec kd-erp qwenpaw cron create \
  --type agent \
  --name "销售日报" \
  --cron "0 9 * * *" \
  --agent-id erp-executive \
  --channel console \
  --target-user <用户ID> \
  --target-session <会话ID> \
  --text "请生成销售日报：查询昨日销售订单汇总，包括订单数量、金额、客户分布"

# 创建应收周报（每周一 09:00）
docker exec kd-erp qwenpaw cron create \
  --type agent \
  --name "应收周报" \
  --cron "0 9 * * 1" \
  --agent-id erp-finance \
  --channel console \
  --target-user <用户ID> \
  --target-session <会话ID> \
  --text "请生成应收周报：查询上周应收账款余额及账龄分析"

# 启用任务
docker exec kd-erp qwenpaw cron state --enable --id <job_id>

# 查看任务列表
docker exec kd-erp qwenpaw cron list --agent-id erp-executive

# 立即执行一次测试
docker exec kd-erp qwenpaw cron run --id <job_id>

# 禁用任务
docker exec kd-erp qwenpaw cron state --disable --id <job_id>

# 删除任务
docker exec kd-erp qwenpaw cron delete --id <job_id>
```

### 预定义报表模板

| 模板 | Cron 表达式 | 执行时间 | 说明 |
|------|-------------|----------|------|
| 销售日报 | 0 9 * * * | 每天 09:00 | 昨日销售订单汇总 |
| 应收周报 | 0 9 * * 1 | 每周一 09:00 | 上周应收账款余额及账龄 |
| 库存月报 | 0 9 1 * * | 每月1日 09:00 | 月末库存汇总 |
| 财务月报 | 0 10 1 * * | 每月1日 10:00 | 月度财务报表摘要 |

注意：定时任务默认创建为 disabled 状态，需先配置好金蝶连接参数，然后手动启用。

---

## 运维操作

### 日常运维

```bash
# 查看实时日志
docker logs -f kd-erp --tail 100

# 查看最近日志
docker logs --tail 500 kd-erp

# 重启服务
docker restart kd-erp

# 进入容器排查
docker exec -it kd-erp bash

# 查看磁盘使用
docker exec kd-erp du -sh /app/working /app/working.secret /app/working.backups
```

### 备份与恢复

```bash
# 备份全部数据
docker run --rm -v kd-erp-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/kd-erp-data-$(date +%Y%m%d).tar.gz -C /data .

# 恢复数据
docker run --rm -v kd-erp-data:/data -v $(pwd):/backup alpine \
  sh -c "cd /data && tar xzf /backup/kd-erp-data-20260101.tar.gz"

# 仅备份权限数据库
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db ".dump" \
  > permissions_backup_$(date +%Y%m%d).sql
```

### 更新镜像

```bash
# 1. 备份数据（见上方备份命令）

# 2. 停止旧容器
docker stop kd-erp && docker rm kd-erp

# 3. 拉取/构建新镜像
docker build -t kingdee-erp-assistant:latest .

# 4. 启动新容器（复用 Volume）
docker run -d \
  --name kd-erp \
  -p 8088:8088 \
  -v kd-erp-data:/app/working \
  -v kd-erp-secrets:/app/working.secret \
  -v kd-erp-backups:/app/working.backups \
  kingdee-erp-assistant:latest

# 5. 重新执行 Agent 初始化（如版本升级涉及 Agent 变更）
docker cp scripts/setup_erp_agents.py kd-erp:/tmp/
docker exec kd-erp python3 /tmp/setup_erp_agents.py
docker restart kd-erp
```

### 审计日志查询

```bash
# 查询最近 20 条写入操作
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db \
  "SELECT datetime(created_at, 'localtime') as time, operator, action, form_id, target
   FROM audit_log ORDER BY created_at DESC LIMIT 20"

# 查询指定用户的操作
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db \
  "SELECT datetime(created_at, 'localtime') as time, action, form_id, target
   FROM audit_log WHERE operator = 'dingtalk:012345' ORDER BY created_at DESC LIMIT 20"

# 查询指定表单的操作
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db \
  "SELECT datetime(created_at, 'localtime') as time, operator, action, target
   FROM audit_log WHERE form_id = 'SAL_SaleOrder' ORDER BY created_at DESC LIMIT 20"

# 查询归档文件
ls -la /app/working/plugin_data/erp/audit_archive/
```

### 常见问题排查

| 症状 | 可能原因 | 排查方法 |
|------|----------|----------|
| 工具调用返回"连接失败" | 金蝶 WebAPI 地址错误 | 检查配置中的 server_url，确保以 /k3cloud/ 结尾 |
| 工具调用返回"认证失败" | App ID/Secret 错误 | 在金蝶后台确认应用授权状态 |
| 工具调用返回"无权限" | 用户权限未配置 | 检查 permissions.db 中该用户的权限记录 |
| Agent 不回复或回复慢 | LLM 模型配额不足 | 检查模型 Provider 的 API Key 和余额 |
| 路由不生效 | 默认 Agent SOUL.md 未更新 | 确认 SOUL.md 包含"ERP 语义路由"段落 |
| Console 显示工具列表为空 | 插件未加载 | 检查 docker logs 中的插件加载日志 |
| 查询结果为空但金蝶有数据 | 组织/权限过滤 | 确认用户的 org_id 和 domains 配置正确 |
| 写入操作被阻止 | 权限为只读 | 检查用户的 access 字段是否为 writeable |

---

## 系统架构

```
                    +---------------+
                    |    Browser    |
                    +-------+-------+
                            | :8088
                    +-------v-------+
                    |    Console    |    前端 UI（品牌已替换）
                    |    (React)    |
                    +-------+-------+
                            | API
              +-------------v-------------+
              |     星智 Server      |    FastAPI + Agent
              |                           |
              +--+--------+--------+------+
                 |        |        |
         +-------v--+ +---v----+ +v---------+
         | Default  | |Finance | | ... x5   |    5 个专业 Agent
         | Router   | | Agent  | | Agents   |
         +----+-----+ +---+----+ +-----+----+
              |           |            |
         +----v-----------v------------v----+
         |         ERP Tool Plugin          |    金蝶工具插件
         |  +---------------------------+  |
         |  | KingdeeBackend (SDK)      |  |
         |  | PermissionManager (SQLite)|  |
         |  | ConfigManager             |  |
         |  +-------------+-------------+  |
         +----------------+----------------+
                          | WebAPI
                 +--------v--------+
                 |  Kingdee K/3    |    金蝶云星空
                 +-----------------+
```

数据流向：
1. 用户在浏览器或钉钉/飞书中提问
2. Console 将消息发送到 Server
3. 默认 Agent 分析意图，路由到对应专业 Agent
4. 专业 Agent 调用 ERP Tool Plugin 中的金蝶工具
5. 工具通过 SDK 调用金蝶 WebAPI
6. 结果原路返回，Agent 整理后回复用户

---

> 星智 -- 系统管理员指南
