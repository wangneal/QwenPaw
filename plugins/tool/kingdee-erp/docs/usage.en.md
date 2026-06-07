# Kingdee ERP Assistant — User Guide

Welcome to the Kingdee ERP Assistant! This guide helps you get started quickly.

---

## Quick Start

### 1. Access the System

Open your browser and navigate to the server address (default: `http://localhost:8088`).

### 2. Select a Role

The system provides 5 specialized roles:

| Role | Use Case | Example Question |
|------|----------|------------------|
| Finance Assistant | Accounting, vouchers, reports | "What is this month's accounts receivable balance?" |
| Sales Assistant | Customers, orders, quotes | "Find all orders for customer 'Huaxing Tech'" |
| Warehouse Assistant | Inventory, stock in/out | "How many 'A4 paper' are currently in stock?" |
| Purchase Assistant | Suppliers, purchase orders | "Compare steel quotes from three suppliers" |
| Executive Assistant | Cross-module summaries | "Quarterly expense summary by department" |

### 3. Start Chatting

Type your question in the chat box. The assistant will query Kingdee ERP and respond automatically.

---

## Tips

### Natural Language Queries

Use everyday language — no need to memorize Kingdee navigation paths:

**Not recommended** (command-style):
> "Execute ExecuteBillQuery, FormId=BD_Customer, fields FName,FNumber"

**Recommended** (natural language):
> "Look up the basic info for customer 'Huaxing Tech'"

### Write Operation Safety

All create/modify/delete operations require your confirmation before execution:

1. Assistant shows an operation summary
2. You confirm ("confirm" / "execute")
3. Assistant executes and returns the result

**No write operations are executed without your explicit confirmation.**

---

## Configuration

Required settings (contact your admin):

| Setting | Description | Required |
|---------|-------------|----------|
| Server URL | Kingdee WebAPI address | Yes |
| Database ID | Account set number | Yes |
| Username | Login username | Yes |
| Password | Login password | Yes |

---

## FAQ

**Q: The assistant says "no permission to query XXX"?**
A: Your current role lacks access. Contact admin to adjust permissions or switch roles.

**Q: Data differs from Kingdee desktop client?**
A: Possible reasons: permission filters, different time windows (default: last 30 days), or data changes after query.

---

> Kingdee ERP Assistant — Making ERP data accessible
