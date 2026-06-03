---
name: kingdee-procurement-fields
description: 金蝶云星空采购域字段映射（采购订单、采购申请、采购入库）
metadata:
  type: knowledge
  version: "1.0"
---

# 金蝶云星空 - 采购域字段映射

## 用途

Agent 查询/操作采购相关单据时，使用本技能确定字段名与中文名的对应关系。涵盖采购订单、采购申请单、采购入库单等核心采购表单。

## 采购域表单一览

| FormId | 中文名 | 说明 |
|--------|--------|------|
| PUR_PurchaseOrder | 采购订单 | 向供应商下达的采购订单 |
| PUR_PurchaseApply | 采购申请单 | 内部采购需求申请 |
| PUR_ReceiveBill | 采购入库单 | 供应商送货入库记录 |

## 字段映射

### 采购订单 (PUR_PurchaseOrder)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识，自动生成 |
| FBillTypeID | 单据类型 | 基础资料 | 采购订单类型 |
| FDate | 日期 | 日期 | 订单日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FSupplierId | 供应商 | 基础资料 | 供应商编码 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FPurchaseOrgId | 采购组织 | 组织 | 采购业务所属组织 |
| FPurchaseDeptId | 采购部门 | 基础资料 | 采购所属部门 |
| FPurchaserGroupId | 采购组 | 基础资料 | 采购所属小组 |
| FPurchaserId | 采购员 | 基础资料 | 负责采购的业务员 |
| FCurrencyId | 币别 | 基础资料 | 交易币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FRequireDeptId | 需求部门 | 基础资料 | 提出采购需求的部门 |
| FRequireStaffId | 需求人 | 基础资料 | 提出采购需求的人 |
| FCreatorId | 创建人 | 创建人 | 订单录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 采购物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 物料规格 |
| FUnitID | 单位 | 单位字段 | 采购计量单位 |
| FQty | 数量 | 数量 | 订货数量 |
| FPrice | 单价 | 价格 | 不含税单价 |
| FTaxPrice | 含税单价 | 价格 | 含税单价 |
| FEntryTaxRate | 税率 | 小数 | 适用税率 |
| FEntryAmount | 金额 | 金额 | 不含税金额 |
| FAllAmount | 价税合计 | 金额 | 含税总金额 |
| FEntryNote | 备注 | 文本 | 行备注 |

---

### 采购申请单 (PUR_PurchaseApply)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 申请单类型 |
| FDate | 日期 | 日期 | 申请日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FApplicationOrgId | 申请组织 | 组织 | 申请所属组织 |
| FRequireDeptId | 需求部门 | 基础资料 | 提出需求的部门 |
| FRequireStaffId | 需求人 | 基础资料 | 提出需求的人 |
| FCreatorId | 创建人 | 创建人 | 申请人 |
| FCreateDate | 创建日期 | 创建日期 | 申请日期 |
| FApproverId | 审核人 | 用户 | 审批人 |
| FApproveDate | 审核日期 | 日期 | 审批时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 申请物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 物料规格 |
| FUnitID | 单位 | 单位字段 | 计量单位 |
| FQty | 申请数量 | 数量 | 申请采购数量 |
| FPrice | 单价 | 价格 | 预估单价 |
| FAmount | 金额 | 金额 | 预估金额 |
| FDateRequired | 需求日期 | 日期 | 期望到货日期 |
| FPurpose | 用途 | 文本 | 采购用途说明 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 采购入库单 (PUR_ReceiveBill)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 入库单类型 |
| FDate | 日期 | 日期 | 入库日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FSupplierId | 供应商 | 基础资料 | 送货供应商 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FPurchaseOrgId | 采购组织 | 组织 | 采购业务所属组织 |
| FStockOrgId | 库存组织 | 组织 | 库存管理组织 |
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
| FStockId | 仓库 | 基础资料 | 入库仓库 |
| FStockStatusId | 库存状态 | 基础资料 | 库存状态（可用/待检等） |
| FLot | 批号 | 批号 | 物料批号 |
| FNote | 备注 | 文本 | 补充说明 |

## 查询技巧

- 供应商字段用 `.FName` 获取名称：`FSupplierId.FName`
- 物料字段用 `.FName` 获取名称、`.FSpecification` 获取规格：`FMaterialId.FName`
- 组织字段：`FPurchaseOrgId.FName`、`FStockOrgId.FName`
- 采购员字段：`FPurchaserId.FName`
- 日期范围查询：`FDate >= '2024-01-01' AND FDate <= '2024-12-31'`
- 含税价筛选：`FTaxPrice > 100`
- 状态筛选：`FDocumentStatus = 'C'` 表示已审核

## 常见查询场景

### 场景1: 查询本月采购订单

```
FormId: PUR_PurchaseOrder
SelectFields: FBillNo,FDate,FSupplierId.FName,FMaterialId.FName,FQty,FAllAmount,FDocumentStatus
Filter: FDate >= '2024-06-01' AND FDate <= '2024-06-30'
```

### 场景2: 查询某供应商的采购订单

```
FormId: PUR_PurchaseOrder
SelectFields: FBillNo,FDate,FMaterialId.FName,FQty,FTaxPrice,FAllAmount,FDocumentStatus
Filter: FSupplierId.FName LIKE '%供应商A%' AND FDocumentStatus = 'C'
```

### 场景3: 查询待审核的采购申请

```
FormId: PUR_PurchaseApply
SelectFields: FBillNo,FDate,FRequireDeptId.FName,FMaterialId.FName,FQty,FDateRequired,FDocumentStatus
Filter: FDocumentStatus = 'A'
```

### 场景4: 查询采购入库明细

```
FormId: PUR_ReceiveBill
SelectFields: FBillNo,FDate,FSupplierId.FName,FMaterialId.FName,FQty,FAmount,FStockId.FName,FLot
Filter: FDate >= '2024-01-01' AND FDocumentStatus = 'C'
```

### 场景5: 按采购员统计订单金额

```
FormId: PUR_PurchaseOrder
SelectFields: FPurchaserId.FName,FQty,FAllAmount
Filter: FDate >= '2024-01-01' AND FDocumentStatus = 'C'
```

### 场景6: 查询某物料的采购入库记录

```
FormId: PUR_ReceiveBill
SelectFields: FBillNo,FDate,FSupplierId.FName,FQty,FAmount,FStockId.FName,FLot
Filter: FMaterialId.FName LIKE '%原材料A%' AND FDocumentStatus = 'C'
```
