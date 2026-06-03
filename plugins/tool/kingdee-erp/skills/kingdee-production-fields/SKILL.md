---
name: kingdee-production-fields
description: 金蝶云星空生产域字段映射（生产订单、BOM）
metadata:
  type: knowledge
  version: "1.0"
---

# 金蝶云星空 - 生产域字段映射

## 用途

Agent 查询/操作生产相关单据时，使用本技能确定字段名与中文名的对应关系。涵盖生产订单（MO）和物料清单（BOM）等核心生产表单。

## 生产域表单一览

| FormId | 中文名 | 说明 |
|--------|--------|------|
| PRD_MO | 生产订单 | 生产任务下达，记录生产计划与实际执行 |
| IC_CBOM | BOM | 物料清单，定义产品的组成结构 |

## 字段映射

### 生产订单 (PRD_MO)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识，生产订单号 |
| FBillTypeID | 单据类型 | 基础资料 | 生产订单类型 |
| FDate | 日期 | 日期 | 订单日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FPrdOrgId | 生产组织 | 组织 | 生产所属组织 |
| FWorkShopId | 车间 | 基础资料 | 生产车间 |
| FMaterialId | 物料 | 基础资料 | 生产产品编码 |
| FMaterialId.FName | 物料名称 | 基础属性 | 产品显示名称 |
| FMaterialId.FSpecification | 规格型号 | 基础属性 | 产品规格 |
| FBomId | BOM | 基础资料 | 使用的物料清单 |
| FUnitID | 单位 | 单位字段 | 生产计量单位 |
| FQty | 生产数量 | 数量 | 计划生产数量 |
| FPlanStartDate | 计划开工日期 | 日期 | 计划开始生产日期 |
| FPlanFinishDate | 计划完工日期 | 日期 | 计划完成生产日期 |
| FActStartDate | 实际开工日期 | 日期 | 实际开始生产日期 |
| FActFinishDate | 实际完工日期 | 日期 | 实际完成生产日期 |
| FStockId | 入库仓库 | 基础资料 | 产成品入库目标仓库 |
| FNote | 备注 | 文本 | 补充说明 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

---

### BOM (IC_CBOM)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBomNo | BOM编号 | 文本 | BOM唯一标识 |
| FMATERIALID | 物料 | 基础资料 | 父项物料（成品） |
| FMATERIALID.FName | 物料名称 | 基础属性 | 父项物料名称 |
| FMATERIALID.FSpecification | 规格型号 | 基础属性 | 父项物料规格 |
| FUnitID | 单位 | 单位字段 | 父项计量单位 |
| FBomQty | BOM用量 | 数量 | 父项基准用量 |
| FDocumentStatus | 状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段（子项物料明细）:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FChildMaterialId | 子项物料 | 基础资料 | 子项物料编码 |
| FChildMaterialId.FName | 子项物料名称 | 基础属性 | 子项物料名称 |
| FChildUnitId | 子项单位 | 单位字段 | 子项计量单位 |
| FChildQty | 子项用量 | 数量 | 子项用量 |
| FScrapRate | 损耗率 | 小数 | 材料损耗百分比 |
| FIsKeyItem | 关键件 | 复选框 | 是否为关键件 |
| FWorkShopId | 车间 | 基础资料 | 使用该子项的车间 |
| FProcessId | 工序 | 基础资料 | 使用该子项的工序 |
| FNote | 备注 | 文本 | 补充说明 |

## 查询技巧

- 生产组织字段：`FPrdOrgId.FName`
- 车间字段：`FWorkShopId.FName`
- BOM 编号筛选：`FBomNo = 'BOM-001'`
- 计划日期范围：`FPlanStartDate >= '2024-01-01' AND FPlanFinishDate <= '2024-03-31'`
- 实际日期范围：`FActStartDate >= '2024-01-01'`
- 子项物料查询：`FChildMaterialId.FName LIKE '%子项名%'`
- 关键件筛选：`FIsKeyItem = true`
- 损耗率筛选：`FScrapRate > 0.05`（损耗率大于5%）

## 常见查询场景

### 场景1: 查询本月生产订单

```
FormId: PRD_MO
SelectFields: FBillNo,FDate,FMaterialId.FName,FQty,FPlanStartDate,FPlanFinishDate,FDocumentStatus
Filter: FDate >= '2024-06-01' AND FDate <= '2024-06-30'
```

### 场景2: 查询某车间的生产任务

```
FormId: PRD_MO
SelectFields: FBillNo,FDate,FMaterialId.FName,FQty,FPlanStartDate,FPlanFinishDate,FDocumentStatus
Filter: FWorkShopId.FName LIKE '%车间A%' AND FDocumentStatus = 'C'
```

### 场景3: 查询超期未完工的生产订单

```
FormId: PRD_MO
SelectFields: FBillNo,FDate,FMaterialId.FName,FQty,FPlanFinishDate,FDocumentStatus
Filter: FPlanFinishDate < '2024-06-30' AND FActFinishDate = NULL AND FDocumentStatus = 'C'
```

### 场景4: 查询某产品的 BOM 结构

```
FormId: IC_CBOM
SelectFields: FBomNo,FMATERIALID.FName,FBomQty,FChildMaterialId.FName,FChildQty,FScrapRate,FIsKeyItem
Filter: FMATERIALID.FName LIKE '%成品A%'
```

### 场景5: 查询 BOM 中包含某子项的产品

```
FormId: IC_CBOM
SelectFields: FBomNo,FMATERIALID.FName,FChildMaterialId.FName,FChildQty,FScrapRate
Filter: FChildMaterialId.FName LIKE '%子项物料%'
```

### 场景6: 查询关键件清单

```
FormId: IC_CBOM
SelectFields: FBomNo,FMATERIALID.FName,FChildMaterialId.FName,FChildQty,FProcessId.FName
Filter: FIsKeyItem = true
```
