---
name: kingdee-inventory-fields
description: 金蝶云星空库存域字段映射（入库、出库、调拨、即时库存）
metadata:
  type: knowledge
  version: "1.0"
---

# 金蝶云星空 - 库存域字段映射

## 用途

Agent 查询/操作库存相关单据时，使用本技能确定字段名与中文名的对应关系。涵盖入库单、其他出库单、调拨申请单、直接调拨单、即时库存等核心库存表单。

## 库存域表单一览

| FormId | 中文名 | 说明 |
|--------|--------|------|
| STK_InStock | 入库单 | 采购入库、产成品入库等 |
| STK_MisDelivery | 其他出库单 | 非销售出库（如报废、赠品） |
| STK_TRANSFERORDER | 调拨申请单 | 跨仓库调拨审批 |
| STK_STKTRANSFERIN | 直接调拨单 | 仓库间直接调拨 |
| STK_Inventory | 即时库存 | 实时库存余额查询 |

## 字段映射

### 入库单 (STK_InStock)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 入库单类型（采购入库/产成品入库等） |
| FDate | 日期 | 日期 | 入库日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FStockOrgId | 库存组织 | 组织 | 库存管理组织 |
| FSupplierId | 供应商 | 基础资料 | 采购入库时的供应商 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 入库物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 物料规格 |
| FUnitID | 单位 | 单位字段 | 入库计量单位 |
| FQty | 实收数量 | 数量 | 实际入库数量 |
| FPrice | 单价 | 价格 | 入库单价 |
| FAmount | 金额 | 金额 | 入库金额 |
| FStockId | 仓库 | 基础资料 | 入库目标仓库 |
| FStockStatusId | 库存状态 | 基础资料 | 库存状态（可用/待检等） |
| FLot | 批号 | 批号 | 物料批号 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 其他出库单 (STK_MisDelivery)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 出库单类型 |
| FDate | 日期 | 日期 | 出库日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FStockOrgId | 库存组织 | 组织 | 库存管理组织 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 出库物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 物料规格 |
| FUnitID | 单位 | 单位字段 | 出库计量单位 |
| FQty | 实发数量 | 数量 | 实际出库数量 |
| FPrice | 单价 | 价格 | 出库单价 |
| FAmount | 金额 | 金额 | 出库金额 |
| FStockId | 仓库 | 基础资料 | 出库来源仓库 |
| FStockStatusId | 库存状态 | 基础资料 | 库存状态 |
| FLot | 批号 | 批号 | 物料批号 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 调拨申请单 (STK_TRANSFERORDER)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 调拨单类型 |
| FDate | 日期 | 日期 | 申请日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FStockOrgId | 库存组织 | 组织 | 库存管理组织 |
| FCreatorId | 创建人 | 创建人 | 申请人 |
| FCreateDate | 创建日期 | 创建日期 | 申请日期 |
| FApproverId | 审核人 | 用户 | 审批人 |
| FApproveDate | 审核日期 | 日期 | 审批时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FSrcStockId | 调出仓库 | 基础资料 | 货物来源仓库 |
| FDestStockId | 调入仓库 | 基础资料 | 货物目标仓库 |
| FMaterialId | 物料 | 基础资料 | 调拨物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FUnitID | 单位 | 单位字段 | 计量单位 |
| FQty | 数量 | 数量 | 调拨数量 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 直接调拨单 (STK_STKTRANSFERIN)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 调拨单类型 |
| FDate | 日期 | 日期 | 调拨日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FStockOrgId | 库存组织 | 组织 | 库存管理组织 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FSrcStockId | 调出仓库 | 基础资料 | 货物来源仓库 |
| FDestStockId | 调入仓库 | 基础资料 | 货物目标仓库 |
| FMaterialId | 物料 | 基础资料 | 调拨物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FUnitID | 单位 | 单位字段 | 计量单位 |
| FQty | 数量 | 数量 | 调拨数量 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 即时库存 (STK_Inventory)

**查询字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 库存物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FMaterialId.FNumber | 物料编码 | 基础属性 | 物料编码值 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 物料规格 |
| FStockOrgId | 库存组织 | 组织 | 库存管理组织 |
| FStockId | 仓库 | 基础资料 | 库存所在仓库 |
| FStockStatusId | 库存状态 | 基础资料 | 可用/待检/冻结等 |
| FLot | 批号 | 批号 | 物料批号 |
| FUnitID | 单位 | 单位字段 | 主计量单位 |
| FBaseQty | 库存数量 | 数量 | 当前库存数量 |
| FAuxUnitId | 辅单位 | 单位字段 | 辅助计量单位 |
| FAuxUnitQty | 辅单位数量 | 数量 | 辅单位库存数量 |
| FSecUnitId | 第二单位 | 单位字段 | 第二计量单位 |
| FSecQty | 第二数量 | 数量 | 第二单位库存数量 |
| FMTONO | 计划跟踪号 | 文本 | MRP计划跟踪号 |

## 查询技巧

- 仓库字段：`FStockId.FName` 获取仓库名称
- 调拨单有两个仓库字段：`FSrcStockId.FName`（调出）、`FDestStockId.FName`（调入）
- 即时库存是查询类表单，没有单头/单据体区分，直接用字段名查询
- 批号筛选：`FLot = 'LOT2024001'`
- 库存状态筛选：`FStockStatusId.FName = '可用'`
- 库存数量筛选：`FBaseQty > 0`（有库存的物料）
- 库存组织筛选：`FStockOrgId.FName = '主工厂'`

## 常见查询场景

### 场景1: 查询某仓库的库存

```
FormId: STK_Inventory
SelectFields: FMaterialId.FName,FMaterialId.FSpecification,FLot,FBaseQty,FUnitID.FName,FStockStatusId.FName
Filter: FStockId.FName LIKE '%主仓库%'
```

### 场景2: 查询某物料的库存分布

```
FormId: STK_Inventory
SelectFields: FStockId.FName,FStockStatusId.FName,FLot,FBaseQty
Filter: FMaterialId.FName LIKE '%物料A%'
```

### 场景3: 查询本月入库明细

```
FormId: STK_InStock
SelectFields: FBillNo,FDate,FMaterialId.FName,FQty,FStockId.FName,FLot,FDocumentStatus
Filter: FDate >= '2024-06-01' AND FDate <= '2024-06-30' AND FDocumentStatus = 'C'
```

### 场景4: 查询其他出库记录

```
FormId: STK_MisDelivery
SelectFields: FBillNo,FDate,FMaterialId.FName,FQty,FStockId.FName,FNote,FDocumentStatus
Filter: FDate >= '2024-01-01' AND FDocumentStatus = 'C'
```

### 场景5: 查询调拨申请

```
FormId: STK_TRANSFERORDER
SelectFields: FBillNo,FDate,FSrcStockId.FName,FDestStockId.FName,FMaterialId.FName,FQty,FDocumentStatus
Filter: FDocumentStatus = 'C'
```

### 场景6: 查询有库存但批号过期的物料

```
FormId: STK_Inventory
SelectFields: FMaterialId.FName,FLot,FBaseQty,FStockId.FName
Filter: FBaseQty > 0
```
