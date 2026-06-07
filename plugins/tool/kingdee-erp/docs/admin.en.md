# System Administrator Guide

This document is for system administrators, covering deployment, configuration, permission management, and operations for the Kingdee ERP Assistant.

---

## 1. Deployment

### 1.1 Docker Deployment (Recommended)

```bash
# Build the white-label image
docker build -t kingdee-erp-assistant:latest .

# Start the service
docker run -d \
  --name kd-erp \
  -p 8088:8088 \
  -v kd-erp-data:/app/working \
  -v kd-erp-secrets:/app/working.secret \
  -v kd-erp-backups:/app/working.backups \
  kingdee-erp-assistant:latest
```

After first startup, access `http://<server-ip>:8088` for the console.

### 1.2 Ports and Storage

| Port | Purpose |
|------|---------|
| 8088 | Web console + API |

| Docker Volume | Container Path | Purpose |
|---------------|----------------|---------|
| `kd-erp-data` | `/app/working` | Agent workspace, plugin data, permission database |
| `kd-erp-secrets` | `/app/working.secret` | LLM API keys and sensitive config |
| `kd-erp-backups` | `/app/working.backups` | Automatic backups |

### 1.3 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QWENPAW_HOST` | Listen address | `0.0.0.0` |
| `QWENPAW_PORT` | Listen port | `8088` |
| `QWENPAW_LOG_LEVEL` | Log level | `INFO` |
| `KINGDEE_WEBUI_BYPASS_PERMISSIONS_ENABLED` | Whether WebUI/Console bypasses Kingdee permission checks | `false` |
| `KINGDEE_PERMISSION_BYPASS_CHANNELS` | Channels allowed to bypass permission checks when the switch above is enabled | `console,webui` |

`KINGDEE_WEBUI_BYPASS_PERMISSIONS_ENABLED` is disabled by default. Set it to `true` only for trusted local console operations, temporary maintenance, or initialization. In production, keep it `false` and configure each user's organization, business domain, and operation permissions in the Kingdee permission management UI. Restart the service or container after changing environment variables, depending on the deployment method.

---

## 2. Kingdee Connection Configuration

### 2.1 Console Configuration

Navigate to **Console → Plugins → Extensible ERP Tool Plugin → Connection Settings**:

| Field | Required | Description |
|-------|----------|-------------|
| Server URL | Yes | WebAPI address, format `http://<IP>/k3cloud/` |
| Database ID | Yes | Kingdee account set identifier |
| Username | Yes | Kingdee login username |
| App ID | Yes | Third-party application App ID |
| App Secret | Yes | Third-party application App Secret |
| Admin Contact | No | Displayed in permission prompts |
| Community Token | No | Required for product Q&A feature |
| Product Name | No | Target product for Q&A (default: Kingdee AI Starry Sky Enterprise) |

### 2.2 Getting Kingdee Application Authorization

1. Log into Kingdee Cloud Starry Sky admin console
2. Navigate to **Base Management → Third-party Applications**
3. Create an application to get **App ID** and **App Secret**
4. Assign required permissions (query, write, etc.) to the application
5. Enter App ID and App Secret in the plugin configuration

### 2.3 Verify Connection

After configuration, test in the console chat:

> "What organizations are available?"

If an organization list is returned, the connection is successful.

---

## 3. Agent Configuration

### 3.1 Run Initialization Script

After first deployment:

```bash
docker cp scripts/setup_erp_agents.py kd-erp:/tmp/
docker exec kd-erp python3 /tmp/setup_erp_agents.py
docker restart kd-erp
```

### 3.2 Agent List

| Agent ID | Name | Domain | Kingdee Prefix |
|----------|------|--------|---------------|
| `erp-finance` | Finance Assistant | Accounting, vouchers, reports | GL_, AR_, AP_ |
| `erp-sales` | Sales Assistant | Orders, customers, quotes | SAL_ |
| `erp-purchase` | Purchase Assistant | Purchase orders, suppliers | PUR_ |
| `erp-inventory` | Inventory Assistant | Stock in/out, inventory count | STK_ |
| `erp-executive` | Executive Assistant | Cross-domain summary | All domains |

### 3.3 Model Configuration

Configure LLM models for each agent:

1. Add a model Provider in **Console → Model Management** (e.g., Qwen, DeepSeek)
2. Select the model in each Agent's settings

**Recommended models**:

| Use Case | Recommended Model | Notes |
|----------|-------------------|-------|
| Daily chat | Qwen-Max / DeepSeek-V3 | Good cost-performance |
| Complex reports | Qwen-Max / GPT-4o | Strong reasoning |
| Product Q&A | Qwen-Plus | Fast response |

### 3.4 Semantic Routing

The default Agent acts as a router, forwarding ERP-related questions to the appropriate specialist Agent.

To modify routing rules, edit the "ERP Semantic Routing" section in `/app/working/workspaces/default/SOUL.md`.

---

## 4. Permission Management

### 4.1 Permission Model

Four-dimensional model: **User x Organization x Domain x Access Level**

| Dimension | Description | Values |
|-----------|-------------|--------|
| User ID | channel:user_id | `wecom:zhangsan` |
| Organization | Kingdee org code | `01`, `02`, `*` (all) |
| Domain | Data scope | `finance`, `sales`, `inventory`, `procurement`, `base` |
| Access | Read/Write | `readonly`, `writeable` |

### 4.2 WebUI Permission Bypass Switch

WebUI and Console channels run Kingdee permission checks by default. To disable permission interception temporarily, explicitly set:

```bash
KINGDEE_WEBUI_BYPASS_PERMISSIONS_ENABLED=true
KINGDEE_PERMISSION_BYPASS_CHANNELS=console,webui
```

This setting only affects permission interception. It does not replace the default organization context. The first use still needs a default organization for the current `agent/channel/user` scope. Later operations keep using that default organization until the user explicitly switches organizations.

### 4.3 Permission Management UI

After installing the `erp-admin` frontend plugin, a **Permission Management** entry appears in the console.

1. Navigate to **Plugins → Kingdee Permission Management**
2. Click **Add Permission**
3. Enter user identifier (e.g., `wecom:zhangsan`)
4. Select organization (org code or `*` for all)
5. Check allowed domains
6. Select access level (readonly / writeable)
7. Save

### 4.4 API-based Permission Management

Endpoint: `/api/erp-permissions`

```bash
# Query user permissions
curl http://localhost:8088/api/erp-permissions?key=wecom:zhangsan

# Set permissions
curl -X POST http://localhost:8088/api/erp-permissions \
  -H "Content-Type: application/json" \
  -d '{
    "key": "wecom:zhangsan",
    "display_name": "Zhang San",
    "org_id": "*",
    "domains": ["finance", "sales"],
    "access": "readonly"
  }'

# Delete permissions
curl -X DELETE http://localhost:8088/api/erp-permissions \
  -H "Content-Type: application/json" \
  -d '{"key": "wecom:zhangsan", "org_id": "*"}'
```

### 4.5 Channel User Identity Mapping

| Channel | User ID Format | Example |
|---------|---------------|---------|
| Console | `console:<user_id>` | `console:default` |
| WeCom | `wecom:<userid>` | `wecom:zhangsan` |
| DingTalk | `dingtalk:<userid>` | `dingtalk:012345` |
| Lark | `lark:<open_id>` | `lark:ou_xxxx` |
| API | `api:<custom_id>` | `api:erp-user-01` |

### 4.6 Default Permissions

The initialization script creates these default permissions:

| User ID | Org | Permission |
|---------|-----|-----------|
| `console:default` | `*` (all) | Full domain, read-write |
| `unknown:unknown` | `*` (all) | Full domain, read-write (debug only) |

**IMPORTANT: Remove the `unknown:unknown` entry in production.**

### 4.7 Permission Database

Location: `/app/working/plugin_data/erp/permissions.db` (SQLite)

```bash
# Backup
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db ".dump" > permissions_backup.sql
```

---

## 5. Security

### 5.1 Write Operation Protection

Three-layer protection for all write operations:

1. **Two-step invocation**: Confirmation step required before execution
2. **FormId validation**: Verifies the operation's form ID is legitimate
3. **Anti-skip mechanism**: Cannot bypass confirmation

### 5.2 Data Isolation

- Organization-level isolation via `org_id` filtering
- Domain-level isolation via `domains` filtering
- Users can only access data within their authorized scope

### 5.3 Sensitive Information

| Data | Storage | Protection |
|------|---------|-----------|
| App Secret | Plugin config | Password-type field, masked in console |
| LLM API Key | `/app/working.secret/` | Separate Docker Volume |
| Permissions | SQLite database | Docker Volume persistence |
| Audit logs | Same as permissions DB | Last 10,000 entries retained |

---

## 6. Operations

### 6.1 Daily Operations

```bash
# View logs
docker logs -f kd-erp --tail 100

# Restart
docker restart kd-erp

# Shell into container
docker exec -it kd-erp bash

# Disk usage
docker exec kd-erp du -sh /app/working /app/working.secret /app/working.backups
```

### 6.2 Backup and Restore

```bash
# Backup all data
docker run --rm -v kd-erp-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/kd-erp-data-$(date +%Y%m%d).tar.gz -C /data .

# Restore data
docker run --rm -v kd-erp-data:/data -v $(pwd):/backup alpine \
  sh -c "cd /data && tar xzf /backup/kd-erp-data-20260101.tar.gz"
```

### 6.3 Image Update

```bash
# 1. Backup data
# 2. Stop and remove old container
docker stop kd-erp && docker rm kd-erp

# 3. Build new image
docker build -t kingdee-erp-assistant:latest .

# 4. Start new container (reuse volumes)
docker run -d \
  --name kd-erp \
  -p 8088:8088 \
  -v kd-erp-data:/app/working \
  -v kd-erp-secrets:/app/working.secret \
  -v kd-erp-backups:/app/working.backups \
  kingdee-erp-assistant:latest

# 5. Re-run agent initialization if needed
docker cp scripts/setup_erp_agents.py kd-erp:/tmp/
docker exec kd-erp python3 /tmp/setup_erp_agents.py
docker restart kd-erp
```

### 6.4 Audit Log

```bash
# Query last 20 operations
docker exec kd-erp sqlite3 /app/working/plugin_data/erp/permissions.db \
  "SELECT datetime(created_at, 'localtime') as time, operator, action, form_id, target
   FROM audit_log ORDER BY created_at DESC LIMIT 20"
```

### 6.5 Troubleshooting

| Symptom | Possible Cause | Resolution |
|---------|---------------|------------|
| "Connection failed" | Wrong WebAPI address | Check server_url ends with `/k3cloud/` |
| "Authentication failed" | Bad App ID/Secret | Verify app authorization in Kingdee admin |
| "No permission" | User not in permissions DB | Check permissions.db for user record |
| Agent not responding | LLM quota exhausted | Check model Provider API key and balance |
| Routing not working | Default Agent SOUL.md missing routing | Verify SOUL.md has "ERP Semantic Routing" section |
| Tools list empty | Plugin not loaded | Check `docker logs kd-erp` for plugin errors |

---

## 7. Scheduled Reports

### 7.1 Creating via CLI

```bash
# Daily sales report (09:00)
docker exec kd-erp qwenpaw cron create \
  --type agent \
  --name "Daily Sales Report" \
  --cron "0 9 * * *" \
  --agent-id erp-executive \
  --channel console \
  --target-user <user_id> \
  --target-session <session_id> \
  --text "Generate sales daily report: query yesterday's sales order summary"

# Enable the job
docker exec kd-erp qwenpaw cron state --enable --id <job_id>

# List jobs
docker exec kd-erp qwenpaw cron list --agent-id erp-executive
```

---

> Kingdee ERP Assistant — System Administrator Guide
