---
name: kingdee-finance-fields
description: 金蝶云星空财务域字段映射（凭证、应收、应付、收付款、发票）
metadata:
  type: knowledge
  version: "1.0"
---

# 金蝶云星空 - 财务域字段映射

## 用途

Agent 查询/操作财务相关单据时，使用本技能确定字段名与中文名的对应关系。涵盖凭证、应收单、应付单、付款申请、付款单、收款单、发票等核心财务表单。

## 财务域表单一览

| FormId | 中文名 | 说明 |
|--------|--------|------|
| GL_Voucher | 凭证 | 会计凭证，记录借贷分录 |
| AR_Receivable | 应收单 | 应收账款单据 |
| AR_RECEIVEBIL | 应收单 | 应收账款单据（另一编码） |
| AP_Payable | 应付单 | 应付账款单据 |
| FIN_PAYAPPLY | 付款申请单 | 付款前的申请审批 |
| FIN_PAYBILL | 付款单 | 实际付款记录 |
| FIN_RECEIVEBIL | 收款单 | 实际收款记录 |
| CN_INVOICE | 发票 | 开票记录 |

## 字段映射

### 凭证 (GL_Voucher)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FVoucherGroupId | 凭证字 | 基础资料 | 如"记"、"收"、"付" |
| FVoucherNo | 凭证号 | 整数 | 凭证序号 |
| FDate | 记账日期 | 日期 | 凭证记账日期 |
| FYear | 会计年度 | 整数 | 如 2024 |
| FPeriod | 会计期间 | 整数 | 如 1-12 |
| FDocumentStatus | 凭证状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FDebitTotal | 借方合计 | 金额 | 借方金额合计 |
| FCreditTotal | 贷方合计 | 金额 | 贷方金额合计 |
| FCreatorId | 制单人 | 创建人 | 凭证录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FCheckerId | 审核人 | 用户 | 审核凭证的人 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FExplanation | 摘要 | 文本 | 分录摘要说明 |
| FAccountId | 科目 | 基础资料 | 会计科目 |
| FAccountName | 科目名称 | 基础属性 | 科目显示名称 |
| FCurrencyId | 币别 | 基础资料 | 记账币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FDC | 借贷方向 | 下拉列表 | D=借方，C=贷方 |
| FAmount | 原币金额 | 金额 | 外币原值 |
| FDebit | 借方金额 | 金额 | 借方发生额 |
| FCredit | 贷方金额 | 金额 | 贷方发生额 |
| FSettleTypeId | 结算方式 | 基础资料 | 如现金、转账等 |
| FSettleNo | 结算号 | 文本 | 结算凭证号 |
| FQty | 数量 | 数量 | 数量核算时使用 |
| FPrice | 单价 | 价格 | 数量核算时使用 |
| FUnitId | 单位 | 基础资料 | 计量单位 |

---

### 应收单 (AR_Receivable / AR_RECEIVEBIL)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 应收单类型 |
| FDate | 业务日期 | 日期 | 业务发生日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FCustomerId | 客户 | 基础资料 | 应收客户 |
| FCustomerId.FName | 客户名称 | 基础属性 | 客户显示名称 |
| FSaleOrgId | 销售组织 | 组织 | 销售业务所属组织 |
| FPayOrgId | 付款组织 | 组织 | 付款所属组织 |
| FCurrencyId | 币别 | 基础资料 | 应收币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FCreatorId | 创建人 | 创建人 | 单据录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMATERIALID | 物料 | 基础资料 | 应收物料 |
| FMaterialName | 物料名称 | 基础属性 | 物料显示名称 |
| FQty | 数量 | 数量 | 应收数量 |
| FPrice | 单价 | 价格 | 单价 |
| FAmount | 应收金额 | 金额 | 不含税金额 |
| FTaxAmount | 税额 | 金额 | 税额 |
| FAllAmount | 价税合计 | 金额 | 含税总金额 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 应付单 (AP_Payable)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 应付单类型 |
| FDate | 业务日期 | 日期 | 业务发生日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FSupplierId | 供应商 | 基础资料 | 应付供应商 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FPurchaseOrgId | 采购组织 | 组织 | 采购业务所属组织 |
| FPayOrgId | 付款组织 | 组织 | 付款所属组织 |
| FCurrencyId | 币别 | 基础资料 | 应付币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FCreatorId | 创建人 | 创建人 | 单据录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMATERIALID | 物料 | 基础资料 | 应付物料 |
| FMaterialName | 物料名称 | 基础属性 | 物料显示名称 |
| FQty | 数量 | 数量 | 应付数量 |
| FPrice | 单价 | 价格 | 单价 |
| FAmount | 金额 | 金额 | 不含税金额 |
| FTaxAmount | 税额 | 金额 | 税额 |
| FAllAmount | 价税合计 | 金额 | 含税总金额 |
| FNote | 备注 | 文本 | 补充说明 |

---

### 付款申请单 (FIN_PAYAPPLY)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 申请单类型 |
| FDate | 申请日期 | 日期 | 申请提交日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FPayOrgId | 付款组织 | 组织 | 付款所属组织 |
| FSupplierId | 供应商 | 基础资料 | 收款供应商 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FCurrencyId | 币别 | 基础资料 | 付款币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FPayAmount | 申请付款金额 | 金额 | 申请金额 |
| FPayTypeId | 付款方式 | 基础资料 | 如电汇、支票等 |
| FPayPurpose | 付款用途 | 文本 | 用途说明 |
| FExpectPayDate | 期望付款日期 | 日期 | 希望付款时间 |
| FNote | 备注 | 文本 | 补充说明 |
| FCreatorId | 创建人 | 创建人 | 申请人 |
| FCreateDate | 创建日期 | 创建日期 | 申请日期 |
| FApproverId | 审核人 | 用户 | 审批人 |
| FApproveDate | 审核日期 | 日期 | 审批时间 |

---

### 付款单 (FIN_PAYBILL)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 付款单类型 |
| FDate | 业务日期 | 日期 | 付款日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FPayOrgId | 付款组织 | 组织 | 付款所属组织 |
| FSupplierId | 供应商 | 基础资料 | 收款供应商 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FCurrencyId | 币别 | 基础资料 | 付款币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FPayAmount | 付款金额 | 金额 | 实付金额 |
| FPayTypeId | 付款方式 | 基础资料 | 如电汇、支票等 |
| FBankAccountId | 银行账户 | 基础资料 | 付款银行账户 |
| FNote | 备注 | 文本 | 补充说明 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

---

### 收款单 (FIN_RECEIVEBIL)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 收款单类型 |
| FDate | 业务日期 | 日期 | 收款日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FReceiveOrgId | 收款组织 | 组织 | 收款所属组织 |
| FCustomerId | 客户 | 基础资料 | 付款客户 |
| FCustomerId.FName | 客户名称 | 基础属性 | 客户显示名称 |
| FCurrencyId | 币别 | 基础资料 | 收款币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FReceiveAmount | 收款金额 | 金额 | 实收金额 |
| FReceiveTypeId | 收款方式 | 基础资料 | 如电汇、支票等 |
| FBankAccountId | 银行账户 | 基础资料 | 收款银行账户 |
| FNote | 备注 | 文本 | 补充说明 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

---

### 发票 (CN_INVOICE)

**单头字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FBillNo | 单据编号 | 文本 | 唯一标识 |
| FBillTypeID | 单据类型 | 基础资料 | 发票类型 |
| FDate | 开票日期 | 日期 | 发票开具日期 |
| FDocumentStatus | 单据状态 | 单据状态 | A创建中/B审核中/C已审核/D重新审核 |
| FInvoiceType | 发票类型 | 下拉列表 | 增值税专用/普通等 |
| FCustomerId | 客户 | 基础资料 | 购方客户 |
| FCustomerId.FName | 客户名称 | 基础属性 | 客户显示名称 |
| FSupplierId | 供应商 | 基础资料 | 销方供应商 |
| FSupplierId.FName | 供应商名称 | 基础属性 | 供应商显示名称 |
| FCurrencyId | 币别 | 基础资料 | 发票币种 |
| FExchangeRate | 汇率 | 小数 | 外币汇率 |
| FCreatorId | 创建人 | 创建人 | 录入人 |
| FCreateDate | 创建日期 | 创建日期 | 录入日期 |
| FApproverId | 审核人 | 用户 | 审核人 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |

**单据体字段:**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FMaterialId | 物料 | 基础资料 | 开票物料 |
| FMaterialId.FName | 物料名称 | 基础属性 | 物料显示名称 |
| FQty | 数量 | 数量 | 开票数量 |
| FPrice | 单价 | 价格 | 单价 |
| FAmount | 金额 | 金额 | 不含税金额 |
| FTaxAmount | 税额 | 金额 | 税额 |
| FAllAmount | 价税合计 | 金额 | 含税总金额 |
| FTaxRate | 税率 | 小数 | 适用税率 |
| FNote | 备注 | 文本 | 补充说明 |

## 查询技巧

- 凭证查询通常按期间筛选：`FYear = 2024 AND FPeriod = 6`
- 应收/应付按客户/供应商筛选：`FCustomerId.FName LIKE '%客户名%'`
- 金额范围查询：`FAllAmount >= 10000 AND FAllAmount <= 100000`
- 基础资料字段用 `.FName` 获取名称：`FCustomerId.FName`、`FSupplierId.FName`
- 状态筛选常用 `FDocumentStatus = 'C'` 表示已审核
- 币别筛选：`FCurrencyId.FName = '人民币'` 或 `FCurrencyId.FNumber = 'PRE001'`
- 收付款单按日期范围查询：`FDate >= '2024-01-01' AND FDate <= '2024-06-30'`

## 常见查询场景

### 场景1: 查询某客户应收账款汇总

```
FormId: AR_Receivable
SelectFields: FBillNo,FDate,FCustomerId.FName,FAmount,FTaxAmount,FAllAmount,FDocumentStatus
Filter: FCustomerId.FName LIKE '%ABC公司%' AND FDocumentStatus = 'C'
```

### 场景2: 查询某期间付款明细

```
FormId: FIN_PAYBILL
SelectFields: FBillNo,FDate,FSupplierId.FName,FPayAmount,FPayTypeId.FName,FDocumentStatus
Filter: FDate >= '2024-01-01' AND FDate <= '2024-03-31' AND FDocumentStatus = 'C'
```

### 场景3: 查询待审核的付款申请

```
FormId: FIN_PAYAPPLY
SelectFields: FBillNo,FDate,FSupplierId.FName,FPayAmount,FPayPurpose,FDocumentStatus
Filter: FDocumentStatus = 'A'
```

### 场景4: 查询凭证分录明细

```
FormId: GL_Voucher
SelectFields: FVoucherNo,FDate,FExplanation,FAccountName,FDC,FDebit,FCredit
Filter: FYear = 2024 AND FPeriod = 6 AND FDocumentStatus = 'C'
```

### 场景5: 查询收款记录

```
FormId: FIN_RECEIVEBIL
SelectFields: FBillNo,FDate,FCustomerId.FName,FReceiveAmount,FReceiveTypeId.FName,FDocumentStatus
Filter: FDate >= '2024-01-01' AND FDocumentStatus = 'C'
```
