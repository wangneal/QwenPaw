---
name: kingdee-field-mapping
description: 金蝶云星空字段映射参考（基于真实数据库元数据，含写入传值格式）
metadata:
  type: knowledge
  version: "3.0"
---

# 金蝶云星空字段映射参考

## 通用关联字段

| 字段 | 说明 | 用法 |
|------|------|------|
| FMaterialId.FNumber | 物料编码 | 查询物料编码 |
| FMaterialId.FName | 物料名称 | 查询物料名称 |
| FCustId.FNumber | 客户编码 | 查询客户编码 |
| FCustId.FName | 客户名称 | 查询客户名称 |
| FSupplierId.FNumber | 供应商编码 | 查询供应商编码 |
| FSupplierId.FName | 供应商名称 | 查询供应商名称 |

## 基础资料特殊编码/名称/内码

一般规则：编码用 `FNumber`，名称用 `FName`，内码用 `FId`。

**例外情况：**

| 基础资料 | 编码 | 名称 | 内码 |
|----------|------|------|------|
| 员工 | FStaffNumber | FName | FId |
| 辅助属性 | — | FDataValue | — |
| 组织 | FNumber | FName | FOrgId |
| 用户 | FNumber | FName | FUserId |

## 单据体相关

| 字段 | 格式 | 示例 |
|------|------|------|
| 单据体内码 | 单据体key + `_` + 分录主键 | FEntity_FEntryId |
| 分录序号 | 单据体key + FSeq | FEntity_FSeq |

## 弹性域维度（核算维度、辅助属性、仓位、职位等级）

| 类型 | 内码 | 名称 |
|------|------|------|
| 辅助属性 | 字段key.维度 | 字段key.维度.FDataValue |
| 核算维度 | 字段key.维度 | 字段key.维度.FName |

示例：`FAuxPropId.FFl00002`（内码），`FAuxPropId.FFl00002.FDataValue`（名称）

## 写入时基础资料字段传值规则

**核心规则：基础资料字段必须用 JSON 对象包裹编码，不能直接传字符串或数字。**

```json
// 正确写法
"FSupplierId": {"FNumber": "S001"}
"FMaterialId": {"FNumber": "M001"}
"FPurchaseOrgId": {"FNumber": "100"}

// 错误写法，会导致保存失败
"FSupplierId": "S001"
"FMaterialId": "M001"
"FPurchaseOrgId": 100
```

**特殊包裹键：**

| 基础资料类型 | 包裹键 | 示例 |
|-------------|--------|------|
| 一般基础资料（供应商/客户/物料/组织/部门/仓库/币别等） | `FNumber` | `{"FNumber": "S001"}` |
| 单据类型 | `FNUMBER`（大写） | `{"FNUMBER": "YSD01_SYS"}` |
| 用户/确认人 | `FUserID` | `{"FUserID": "100001"}` |
| 联系人 | `FCONTACTNUMBER` | `{"FCONTACTNUMBER": "001"}` |
| 辅助属性（非库存单据） | 空对象 | `{}` |
| 辅助属性（库存单据） | 必须传实际值 | `{"FFl00001": "值"}` |

详细写入规范和 Model JSON 结构范式请参阅 **kingdee-write-safety** 技能。
| FStockId.FName | 仓库名称 | 查询仓库名称 |
| FOrgId.FNumber | 组织编码 | 查询组织编码 |
| FOrgId.FName | 组织名称 | 查询组织名称 |
| FDeptId.FName | 部门名称 | 查询部门名称 |
| FSalerId.FName | 销售员名称 | 查询销售员名称 |
| FCurrencyId.FName | 币别名称 | 查询币别名称 |

## 业务域字段速查

### 财务域

**GL_Voucher（凭证）**
- FAccountBookID（账簿）, FDate（日期）, FYear（年度）, FPeriod（期间）
- FDebitTotal（借方合计）, FCreditTotal（贷方合计）, FDocumentStatus（状态）

**AR_Receivable（应收单）**
- FCUSTOMERID（客户）, FSALEORGID（销售组织）, FSALEDEPTID（销售部门）
- FSALEGROUPID（销售组）, FSALEERID（销售员）, FDocumentStatus（状态）

**AP_Payable（应付单）**
- FSUPPLIERID（供应商）, FPURCHASEORGID（采购组织）, FALLOCATESTATUS（分配状态）
- FHOOKSTATUS（钩稽状态）, FBUSINESSTYPE（业务类型）, FCOSTID（费用）

### 销售域

**SAL_SaleOrder（销售订单）**
- FCustId（客户）, FSaleDeptId（销售部门）, FSaleGroupId（销售组）
- FSalerId（销售员）, FReceiveId（收货方）, FSettleId（结算方）

### 采购域

**PUR_PurchaseOrder（采购订单）**
- FSupplierId（供应商）, FPurchaserGroupId（采购组）, FPurchaseDeptId（采购部门）
- FCreatorId（创建人）, FCreateDate（创建日期）, FApproverId（审核人）

### 库存域

**STK_InStock（入库单）**
- FDemandOrgId（需求组织）, FPurchaseOrgId（采购组织）, FSupplierId（供应商）
- FStockerGroupId（仓管组）, FStockDeptId（仓储部门）, FStockerId（仓管员）

### 基础资料

**BD_Material（物料）**
- FErpClsID（物料属性）, FStoreUnitID（库存单位）, FMnemonicCode（助记码）
- FIsInventory（允许库存）, FIsSale（允许销售）, FIsAsset（允许资产）

**BD_Customer（客户）**
- FShortName（简称）, FCountry（国家）, FProvincial（省份）
- FZip（邮编）, FTel（电话）, FTaxRegisterCode（税号）

**BD_Supplier（供应商）**
- FShortName（简称）, FZip（邮编）, FPurchaserGroupId（采购组）
- FMinPOValue（最小订单额）, FNeedConfirm（需要确认）

## 字段类型速查

| 类型 | 说明 | 类型 | 说明 |
|------|------|------|------|
| 文本 | 基础资料 | 组织 | 创建人 |
| 创建日期 | 修改人 | 修改日期 | 用户 |
| 日期 | 金额 | 数量 | 价格 |
| 小数 | 折扣率 | 复选框 | 整数 |
| 基础资料属性 | 单据状态 | 单据编号 | 单据类型 |
| 下拉列表 | 单位字段 | 辅助属性 | 源单类型 |
| 源单编号 | 税率 | 批号 | 日期时间 |

## 状态码

| 字段 | 值 | 含义 |
|------|---|------|
| FDocumentStatus | A | 创建中 |
| FDocumentStatus | B | 审核中 |
| FDocumentStatus | C | 已审核 |
| FDocumentStatus | D | 重新审核 |
| FClosedStatus | A | 未关闭 |
| FClosedStatus | B | 已关闭 |
| FApproveStatus | A | 未审核 |
| FApproveStatus | B | 审核中 |
| FApproveStatus | C | 已审核 |
