---
name: erp-cross-system-push
description: 跨ERP系统数据下推 - 将单据数据从一个系统推送到另一个系统（如金蝶采购申请→SAP采购订单）
metadata:
  type: knowledge
  version: "1.0"
---

# 跨ERP系统数据下推

## 下推场景

跨系统下推将一个ERP系统中的单据数据传递到另一个系统：
- **采购申请传递**：金蝶采购申请下推为SAP采购订单
- **销售订单同步**：金蝶销售订单同步到SAP生成交货单
- **入库确认回写**：SAP入库完成后回写金蝶入库单状态

## 重要说明

跨系统下推**不是一步完成的工具调用**，而是多步组合操作。每一步独立执行，中间结果影响下一步参数。

## 下推步骤（四步）

### 第1步：从源系统查询原始单据

使用 `kingdee_query_bill` 或 `erp_unified_query` 查询需要下推的单据。

### 第2步：转换数据格式

将源系统字段映射为目标系统字段。Agent 根据业务规则完成映射转换。

### 第3步：写入目标系统

使用 `kingdee_save_bill` 写入。当前只有金蝶后端可用，SAP/用友后端待开发。

### 第4步：展示操作摘要并确认

写入前**必须**展示摘要，获得用户明确确认后才执行。摘要包括：源系统和单号、目标系统和表单、关键字段值、预计记录数。

## 下推示例：金蝶采购申请→SAP采购订单

**查询采购申请：**
```
工具: kingdee_query_bill
参数:
  form_id: PUR_Requisition
  field_keys: FBillNo,FDate,FMaterialId.FNumber,FMaterialId.FName,FQty,FPrice,FAmount
  filter_string: FDocumentStatus = 'C' and FBillNo = 'REQ2024001'
```

**字段映射：** FBillNo→RefNumber, FMaterialId.FNumber→MaterialCode, FQty→Quantity, FPrice→Price, FAmount→Amount

**写入目标系统（待SAP后端实现）：**
```
工具: kingdee_save_bill
参数:
  form_id: PUR_PurchaseOrder
  data: {
    "Model": {
      "FSupplierId": {"FNumber": "转换后的供应商编码"},
      "FPurchaseOrgId": {"FNumber": "组织编码"},
      "FPOOrderEntry": [{
        "FMaterialId": {"FNumber": "转换后的物料编码"},
        "FQty": 100,
        "FPrice": 50.0
      }]
    }
  }
```
⚠️ 注意：基础资料字段必须用 `{"FNumber": "编码"}` 包裹，禁止直接传字符串。详见 **kingdee-write-safety** 技能。

**确认摘要：**
> 即将执行跨系统下推：金蝶 REQ2024001 → SAP 采购订单，物料：原材料A，数量：100，单价：50.00。请确认是否执行？

## 权限检查

需同时具备源系统**读取权限**和目标系统**写入权限**。任一不足时返回错误提示。

## 写入安全规范

参照 `kingdee-write-safety` Skill 的确认流程：写入前展示摘要、获得确认、返回结果、失败时提供回滚建议。

## 当前限制

- 只有金蝶后端已实现，下推到SAP/用友需等对应后端开发
- 字段映射规则需根据实际业务场景定制
- 批量下推时需注意事务一致性
