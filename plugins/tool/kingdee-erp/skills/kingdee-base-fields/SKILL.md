---
name: kingdee-base-fields
description: 金蝶云星空基础资料字段映射（物料、客户、供应商）
metadata:
  type: knowledge
  version: "1.0"
---

# 金蝶云星空 - 基础资料字段映射

## 用途

Agent 查询/操作基础资料时，使用本技能确定字段名与中文名的对应关系。涵盖物料、客户、供应商三大核心基础资料。

## 基础资料表单一览

| FormId | 中文名 | 说明 |
|--------|--------|------|
| BD_Material | 物料 | 产品、原材料、半成品等物料主数据 |
| BD_Customer | 客户 | 客户主数据，含联系方式、结算信息 |
| BD_Supplier | 供应商 | 供应商主数据，含联系方式、付款信息 |

## 字段映射

### 物料 (BD_Material)

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FNumber | 物料编码 | 文本 | 物料唯一编码 |
| FName | 物料名称 | 多语言文本 | 物料显示名称 |
| FSpecification | 规格型号 | 多语言文本 | 物料规格型号 |
| FErpClsID | 物料属性 | 下拉列表 | 外购/自制/委外等分类 |
| FMaterialGroup | 物料分组 | 基础资料 | 物料所属分组 |
| FBaseUnitId | 基本单位 | 基础资料 | 基本计量单位 |
| FStoreUnitID | 库存单位 | 基础资料 | 库存管理计量单位 |
| FSaleUnitId | 销售单位 | 基础资料 | 销售业务计量单位 |
| FPurchaseUnitId | 采购单位 | 基础资料 | 采购业务计量单位 |
| FIsInventory | 允许库存 | 复选框 | 是否允许库存管理 |
| FIsSale | 允许销售 | 复选框 | 是否允许销售 |
| FIsPurchase | 允许采购 | 复选框 | 是否允许采购 |
| FIsProduce | 允许生产 | 复选框 | 是否允许生产 |
| FIsAsset | 允许资产 | 复选框 | 是否为资产类物料 |
| FDefaultVendor | 默认供应商 | 基础资料 | 默认采购供应商 |
| FPurchaserId | 采购员 | 基础资料 | 默认采购员 |
| FPlanerID | 计划员 | 基础资料 | 物料计划员 |
| FMaxQty | 最大库存量 | 小数 | 库存上限 |
| FMinQty | 安全库存量 | 小数 | 库存下限 |
| FOrderQty | 经济批量 | 小数 | 经济订货批量 |
| FIsEnable | 是否启用 | 复选框 | 物料是否启用 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |
| FApproverId | 审核人 | 用户 | 审核人 |

---

### 客户 (BD_Customer)

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FNumber | 客户编码 | 文本 | 客户唯一编码 |
| FName | 客户名称 | 多语言文本 | 客户全称 |
| FShortName | 客户简称 | 多语言文本 | 客户简短名称 |
| FGroupCustId | 集团客户 | 基础资料 | 所属集团客户 |
| FSupplierId | 对应供应商 | 基础资料 | 关联的供应商档案 |
| FTradingCurrencyId | 交易币别 | 基础资料 | 默认交易币种 |
| FSalDeptId | 销售部门 | 基础资料 | 负责销售的部门 |
| FSalGroupId | 销售组 | 基础资料 | 负责销售的小组 |
| FSeller | 销售员 | 基础资料 | 负责销售的业务员 |
| FPriceListId | 价目表 | 基础资料 | 适用的价目表 |
| FDiscountListId | 折扣表 | 基础资料 | 适用的折扣表 |
| FSettleTypeId | 结算方式 | 基础资料 | 默认结算方式 |
| FRecConditionId | 收款条件 | 基础资料 | 收款条件（如30天账期） |
| FTaxRegisterCode | 税务登记号 | 文本 | 客户税号 |
| FBankCode | 银行账号 | 文本 | 客户银行账号 |
| FAddress | 地址 | 文本 | 客户地址 |
| FTel | 电话 | 文本 | 联系电话 |
| FEMail | 邮箱 | 文本 | 联系邮箱 |
| FContact | 联系人 | 文本 | 主要联系人 |
| FIsCreditCheck | 是否信用管理 | 复选框 | 是否启用信用管控 |
| FIsUsed | 是否启用 | 复选框 | 客户是否启用 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |
| FApproverId | 审核人 | 用户 | 审核人 |

---

### 供应商 (BD_Supplier)

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| FNumber | 供应商编码 | 文本 | 供应商唯一编码 |
| FName | 供应商名称 | 多语言文本 | 供应商全称 |
| FShortName | 供应商简称 | 多语言文本 | 供应商简短名称 |
| FParentSupplierId | 上级供应商 | 基础资料 | 所属上级供应商 |
| FCustomerId | 对应客户 | 基础资料 | 关联的客户档案 |
| FPayCurrencyId | 付款币别 | 基础资料 | 默认付款币种 |
| FPurchaserGroupId | 采购组 | 基础资料 | 负责采购的小组 |
| FPayCondition | 付款条件 | 基础资料 | 付款条件（如30天账期） |
| FSettleTypeId | 结算方式 | 基础资料 | 默认结算方式 |
| FTaxRegisterCode | 税务登记号 | 文本 | 供应商税号 |
| FBankCode | 银行账号 | 文本 | 供应商银行账号 |
| FBankHolder | 开户名 | 文本 | 银行开户名称 |
| FOpenBankName | 开户银行 | 多语言文本 | 开户银行名称 |
| FAddress | 地址 | 文本 | 供应商地址 |
| FTel | 电话 | 文本 | 联系电话 |
| FEMail | 邮箱 | 文本 | 联系邮箱 |
| FContact | 联系人 | 文本 | 主要联系人 |
| FLegalPerson | 法人代表 | 文本 | 法人姓名 |
| FRegisterFund | 注册资本 | 小数 | 注册资本金额 |
| FTransportDays | 运输天数 | 整数 | 平均运输天数 |
| FBusinessStatus | 经营状态 | 单据状态 | 供应商经营状态 |
| FApproveDate | 审核日期 | 日期 | 审核时间 |
| FApproverId | 审核人 | 用户 | 审核人 |

## 查询技巧

- 物料编码/名称是最常用的查询条件：`FNumber LIKE 'M001%'`、`FName LIKE '%螺丝%'`
- 物料属性筛选：`FErpClsID = 1`（1=外购，2=自制，3=委外）
- 客户/供应商名称模糊查询：`FName LIKE '%公司名%'`
- 客户/供应商编码精确查询：`FNumber = 'C001'`
- 启用状态筛选：`FIsEnable = true`（物料）、`FIsUsed = true`（客户）
- 分组筛选：`FMaterialGroup.FName LIKE '%原材料%'`
- 信用管理筛选：`FIsCreditCheck = true`
- 基础资料没有单据状态字段，但有审核人/审核日期
- 基础资料没有单头/单据体区分，所有字段平级

## 常见查询场景

### 场景1: 搜索物料

```
FormId: BD_Material
SelectFields: FNumber,FName,FSpecification,FErpClsID,FBaseUnitId.FName,FIsEnable
Filter: FName LIKE '%电机%'
```

### 场景2: 查询某分组下的物料

```
FormId: BD_Material
SelectFields: FNumber,FName,FSpecification,FBaseUnitId.FName,FIsEnable
Filter: FMaterialGroup.FName LIKE '%原材料%' AND FIsEnable = true
```

### 场景3: 查询客户列表

```
FormId: BD_Customer
SelectFields: FNumber,FName,FShortName,FTel,FContact,FIsUsed
Filter: FIsUsed = true
```

### 场景4: 搜索特定客户

```
FormId: BD_Customer
SelectFields: FNumber,FName,FShortName,FAddress,FTel,FContact,FBankCode
Filter: FName LIKE '%科技%'
```

### 场景5: 查询供应商列表

```
FormId: BD_Supplier
SelectFields: FNumber,FName,FShortName,FTel,FContact,FIsUsed
Filter: FIsUsed = true
```

### 场景6: 查询启用信用管理的客户

```
FormId: BD_Customer
SelectFields: FNumber,FName,FShortName,FTaxRegisterCode,FRecConditionId.FName
Filter: FIsCreditCheck = true AND FIsUsed = true
```

### 场景7: 查询安全库存不足的物料

```
FormId: BD_Material
SelectFields: FNumber,FName,FSpecification,FMinQty,FBaseUnitId.FName
Filter: FMinQty > 0 AND FIsEnable = true
```
