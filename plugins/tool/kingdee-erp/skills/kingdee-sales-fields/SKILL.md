---
name: kingdee-sales-fields
description: 金蝶云星空销售域字段映射（销售订单、销售出库单）
metadata:
  type: knowledge
  version: "1.0"
---

# 金蝶云星空 - 销售域字段映射

## 用途

Agent 查询/操作销售相关单据时，使用本技能确定字段名与中文名的对应关系。涵盖销售订单、销售出库单等核心销售表单。

## 销售域表单一览

| FormId | 中文名 | 说明 |
|--------|--------|------|
| SAL_SaleOrder | 销售订单 | 客户下单记录，销售业务起点 |
| SAL_OutStock | 销售出库单 | 销售发货出库记录 |
| SAL_SaleOutStock | 销售出库单 | 销售出库单（另一编码） |

## 字段映射

### 销售订单 (SAL_SaleOrder)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识，自动生成 |
| FBillTypeID | 单据类型 | 基础资料 | 销售订单类型 |
| FDate | 日期 | 日期 | 订单日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FCustId | 客户 | 基础资料 | 下单客户 |
| FCustId.FName | 客户名称 | 基础属性 | 客户显示名称 |
| FSaleOrgId | 销售组织 | 组织 | 销售业务所属组织 |
| FSaleDeptId | 销售部门 | 基础资料 | 销售所属部门 |
| FSaleGroupId | 销售组 | 基础资料 | 销售所属小组 |
| FSalerId | 销售员 | 基础资料 | 负责销售的业务员 |
| FCurrencyId | 币别 | 基础资料 | 交易币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FSettleId | 结算方 | 基础资料 | 结算主体 |
| FReceiveId | 收货方 | 基础资料 | 货物接收方 |
| FChargeId | 付款方 | 基础资料 | 付款责任方 |
| FCreatorId | 创建人 | 创建人 | 订单录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FModifierId | 修改人 | 修改人 | 最后修改人 |
| FModifyDate | 修改日期 | 修改日期 | 最后修改时间 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 销售物料编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 物料规格 |
| FUnitID | 单位 | 单位字段 | 销售计量单位 |
| FQty | 数量 | 数量 | 订货数量 |
| FPrice | 单价 | 价格 | 不含税单价 |
| FTaxPrice | 含税单价 | 价格 | 含税单价 |
| FEntryTaxRate | 税率 | 小数 | 适用税率 |
| FEntryTaxAmount | 税额 | 金额 | 税额 |
| FAmount | 金额 | 金额 | 不含税金额 |
| FAllAmount | 价税合计 | 金额 | 含税总金额 |
| FEntryNote | 备注 | 文本 | 行备注 |

---

### 销售出库单 (SAL_OutStock / SAL_SaleOutStock)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 出库单类型 |
| FDate | 日期 | 日期 | 出库日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FCustomerID | 客户 | 基础资料 | 收货客户 |
| FCustomerID.FName | 客户名称 | 基础属性 | 客户显示名称 |
| FSaleOrgId | 销售组织 | 组织 | 销售业务所属组织 |
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
| FStockId | 仓库 | 基础资料 | 出库仓库 |
| FStockStatusId | 库存状态 | 基础资料 | 库存状态（可用/待检等） |
| FLot | 批号 | 批号 | 物料批号 |
| FNote | 备注 | 文本 | 补充说明 |

## 查询技巧

- 客户字段用 `.FName` 获取名称：`FCustId.FName`、`FCustomerID.FName`
- 物料字段用 `.FName` 获取名称、`.FSpecification` 获取规格：`FMaterialId.FName`、`FMaterialId.FSpecification`
- 组织字段用 `.FName` 或 `.FNumber`：`FSaleOrgId.FName`、`FSaleOrgId.FNumber`
- 销售员字段：`FSalerId.FName` 获取销售员名称
- 日期范围查询：`FDate >= '2024-01-01' AND FDate <= '2024-12-31'`
- 金额筛选：`FAllAmount > 10000`
- 状态筛选：`FDocumentStatus = 'C'` 表示已审核

## 常见查询场景

### 场景1: 查询本月销售订单

```
FormId: SAL_SaleOrder
SelectFields: FBillNo,FDate,FCustId.FName,FMaterialId.FName,FQty,FAllAmount,FDocumentStatus
Filter: FDate >= '2024-06-01' AND FDate <= '2024-06-30'
```

### 场景2: 查询某客户的销售订单

```
FormId: SAL_SaleOrder
SelectFields: FBillNo,FDate,FSalerId.FName,FMaterialId.FName,FQty,FAllAmount,FDocumentStatus
Filter: FCustId.FName LIKE '%ABC公司%' AND FDocumentStatus = 'C'
```

### 场景3: 查询待出库的销售订单

```
FormId: SAL_SaleOrder
SelectFields: FBillNo,FDate,FCustId.FName,FMaterialId.FName,FQty,FDocumentStatus
Filter: FDocumentStatus = 'C'
```

### 场景4: 查询销售出库明细

```
FormId: SAL_OutStock
SelectFields: FBillNo,FDate,FCustomerID.FName,FMaterialId.FName,FQty,FAmount,FStockId.FName,FLot
Filter: FDate >= '2024-01-01' AND FDocumentStatus = 'C'
```

### 场景5: 按销售员统计订单

```
FormId: SAL_SaleOrder
SelectFields: FSalerId.FName,FQty,FAllAmount
Filter: FDate >= '2024-01-01' AND FDocumentStatus = 'C'
```

### 场景6: 查询含特定物料的出库记录

```
FormId: SAL_OutStock
SelectFields: FBillNo,FDate,FCustomerID.FName,FQty,FAmount,FStockId.FName,FLot
Filter: FMaterialId.FName LIKE '%产品A%' AND FDocumentStatus = 'C'
```
