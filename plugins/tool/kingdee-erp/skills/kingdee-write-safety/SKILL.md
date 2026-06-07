---
name: kingdee-write-safety
description: 金蝶云星空写入操作安全规范（含基础资料字段传值规则）
metadata:
  type: knowledge
  version: "2.0"
---

# 金蝶云星空写入操作安全规范

## 写入操作安全原则

1. **双步调用原则（硬性防护）**：所有写入操作采用双步调用机制，代码层面强制执行：
   - 第一步：调用写入工具（默认 execute=False），仅返回操作预览，**不执行任何写入**
   - 第二步：用户确认后，再次调用写入工具（execute=True），才执行实际操作
   - 即使模型不遵守文字指令，代码也保证第一次调用不可能执行写入
2. **防跳步原则（硬性防护）**：代码追踪预览状态，未预览过则拒绝 execute=True：
   - 模型直接传 `execute=True` 跳过确认时，会被代码阻止并返回错误
   - 每次预览会生成操作指纹（form_id + 参数hash），执行时必须匹配
   - 这是防止模型"聪明地"直接传 `execute=True` 的关键防护
3. **FormId校验原则（硬性防护）**：代码校验 FormId 是否在白名单中：
   - 白名单来源：metadata/common_tables.json + metadata/domain_tables.json
   - 不在白名单的 FormId 直接拒绝执行，返回校验错误
   - 防止模型编造不存在的表单ID
4. **空结果声明原则（硬性防护）**：查询返回空结果时，代码强制附加防幻觉声明：
   - 固定提示“系统中未找到匹配数据”，并禁止将空结果作为已有业务数据处理
   - 防止模型对空结果编造后续回答
5. **摘要原则**：操作预览必须包含：操作类型、目标表单、关键字段值（单号、日期、金额等）
6. **删除原则**：删除操作预览中包含不可逆警告
7. **审核原则**：审核操作预览中包含"审核后不可修改"警告
8. **下推原则**：下推操作预览中说明源单→目标单的转换关系
9. **防幻觉原则**：所有编码值（供应商/物料/组织/部门/单据类型）必须先通过查询工具获取，禁止猜测或编造
10. **歧义追问原则**：用户指令缺少单据编号、操作类型或必填参数时，必须追问具体信息，不得自行决定或猜测
11. **先查后写原则**：写入前必须先用查询工具验证所有参数值的真实性和准确性

## 写入工具使用说明

### kingdee_save_bill（新增/修改单据）
- 用途：创建新单据或修改已有单据
- 必填参数：`form_id`（表单标识）、`model`（单据JSON数据）、`org_id`（组织ID）
- 注意：修改时需提供单据内码

**基础资料字段传值规则（极易出错，必须严格遵守）**

保存接口中，基础资料类型字段（供应商、客户、物料、组织、部门、仓库等）**不能直接传字符串或数字**，必须用 JSON 对象包裹编码，格式为 `{"FNumber": "编码值"}`。

```json
// 正确写法
{
  "FSupplierId": {"FNumber": "S001"},
  "FMaterialId": {"FNumber": "M001"},
  "FPurchaseOrgId": {"FNumber": "100"},
  "FPurchaseDeptId": {"FNumber": "D001"},
  "FStockId": {"FNumber": "WH001"},
  "FCustId": {"FNumber": "C001"},
  "FCurrencyId": {"FNumber": "PRE001"}
}

// 错误写法，会导致保存失败或字段丢失
{
  "FSupplierId": "S001",
  "FMaterialId": "M001",
  "FPurchaseOrgId": 100
}
```

**特殊标识符注意：** 部分基础资料字段不使用 `FNumber`，而是使用特定标识符：

| 字段场景 | 正确包裹键 | 示例 |
|----------|-----------|------|
| 一般基础资料 | `FNumber` | `{"FNumber": "S001"}` |
| 单据类型（FBillTypeId 等） | `FNUMBER`（大写） | `{"FNUMBER": "YSD01_SYS"}` |
| 用户/确认人（FConfirmerId 等） | `FUserID` | `{"FUserID": "100001"}` |
| 联系人（FProviderContactId 等） | `FCONTACTNUMBER` | `{"FCONTACTNUMBER": "001"}` |
| 辅助属性（非库存单据） | 传空对象 `{}` | `{}` |
| 辅助属性（库存单据） | 必须传实际值 | `"FAuxPropId": {"FFl00001": "值"}` |
| 预付单（FPayAdvanceBillId 等） | 传空对象 `{}` | `{}` |

**写入前务必：** 先用 `kingdee_query_metadata` 查询表单字段定义，确认字段类型。如果是基础资料类型，必须按上述规则包裹传值。

## Model JSON 结构范式

`kingdee_save_bill` 的 `model` 参数必须遵循金蝶 WebAPI 的标准结构。完整范式如下：

```json
{
  "NeedUpDateFields": [],
  "NeedReturnFields": [],
  "IsDeleteEntry": "true",
  "SubSystemId": "",
  "IsVerifyBaseDataField": "false",
  "IsEntryBatchFill": "true",
  "ValidateFlag": "true",
  "NumberSearch": "true",
  "IsAutoAdjustField": "false",
  "InterationFlags": "",
  "IgnoreInterationFlag": "",
  "IsControlPrecision": "false",
  "ValidateRepeatJson": "false",
  "Model": {
    "FID": 0,
    "FBillTypeId": { "FNUMBER": "" },
    "FBillNo": "",
    "FDate": "1900-01-01",
    "FXXXXOrgId": { "FNumber": "" },
    "FXXXXDeptId": { "FNumber": "" },
    "FDetailEntity": [
      {
        "FEntryID": 0,
        "FMaterialId": { "FNumber": "" },
        "FUnitId": { "FNumber": "" },
        "FQty": 0,
        "FPrice": 0,
        "FAuxPropId": {},
        "FLot": { "FNumber": "" }
      }
    ],
    "FFinanceEntity": {
      "FEntryId": 0,
      "FSettleModeId": { "FNumber": "" },
      "FCurrencyId": { "FNumber": "" }
    }
  }
}
```

**结构要点：**

1. **外层参数**：`NeedUpDateFields`（需更新字段）、`NumberSearch`（按编码匹配）、`ValidateFlag`（校验标志）等控制参数
2. **Model 对象**：单据头字段 + 单据体嵌套
3. **单据头**：基础资料字段用 `{"FNumber": "值"}` 包裹，文本/数值/日期直接传值
4. **单据体**：数组格式 `[]`，每行一个对象，行内基础资料同样包裹
5. **财务信息体**：对象格式 `{}`，基础资料同样包裹
6. **新增单据**：`FID` 传 0 或省略；**修改单据**：`FID` 传单据内码，`NeedUpDateFields` 填写需更新的字段标识

**各字段类型传值对照：**

| 字段类型 | 传值方式 | 示例 |
|----------|---------|------|
| 基础资料 | `{"FNumber": "编码"}` | `"FSupplierId": {"FNumber": "S001"}` |
| 文本 | 直接字符串 | `"FBillNo": "PO001"` |
| 数值 | 直接数字 | `"FQty": 100, "FPrice": 50.0` |
| 日期 | 字符串 `"YYYY-MM-DD"` | `"FDate": "2024-01-15"` |
| 布尔 | 字符串 `"true"/"false"` | `"FGiveAway": "false"` |
| 辅助属性（非库存单据） | 传空对象 `{}` | `{}` |
| 辅助属性（库存单据） | 必须传实际值 | `"FAuxPropId": {"FFl00001": "值"}` |

### kingdee_delete_bill（删除单据）
- 用途：删除单据
- 必填参数：`form_id`、`bill_no`（单号）
- 限制：仅限未审核单据

### kingdee_submit_bill（提交单据）
- 用途：提交单据进入审批流程
- 必填参数：`form_id`、`bill_no`

### kingdee_audit_bill（审核单据）
- 用途：审核单据
- 必填参数：`form_id`、`bill_no`
- 注意：审核后不可修改，需反审核后才能修改

### kingdee_unaudit_bill（反审核单据）
- 用途：反审核已审核单据
- 必填参数：`form_id`、`bill_no`
- 限制：仅限有权限用户

### kingdee_push_bill（下推单据）
- 用途：从源单下推生成目标单
- 必填参数：`form_id`（源单表单）、`bill_no`（源单单号）、`target_form_id`（目标表单）

## 单据状态流转

```
创建(A) → 提交(B) → 审核(C) → 反审核(A)
```

状态说明：
- A：创建（可修改、可删除）
- B：审核中（不可修改）
- C：已审核（不可修改，需反审核）
- D：重新审核

## 写入操作预览模板

执行任何写入操作前，必须向用户展示以下确认信息：

```
写入操作预览
操作类型: [新增/修改/删除/审核/下推]
FormId: [表单标识]
组织: [组织ID]
参数:
- 目标: [表单名称] [单号]
- 内容: [关键信息摘要]
执行要求: 仅在用户明确确认后，使用相同工具并设置 execute=True 执行。
```

## 常见场景示例

### 新增销售订单
```
写入操作预览
操作类型: 新增
FormId: SAL_SaleOrder
组织: 01
参数:
- 目标: 销售订单
- 内容: 客户=某某公司, 日期=2024-01-15, 金额=10000.00
执行要求: 仅在用户明确确认后，使用相同工具并设置 execute=True 执行。
```

### 删除采购订单
```
写入操作预览
操作类型: 删除
FormId: PUR_PurchaseOrder
组织: 01
参数:
- 目标: 采购订单 PUR00001
- 内容: 此操作不可逆，删除后无法恢复
执行要求: 仅在用户明确确认后，使用相同工具并设置 execute=True 执行。
```

### 审核应收单
```
写入操作预览
操作类型: 审核
FormId: AR_Receivable
组织: 01
参数:
- 目标: 应收单 AR00001
- 内容: 客户=某某公司, 金额=5000.00
- 检查要求: 单据已检查无误
执行要求: 仅在用户明确确认后，使用相同工具并设置 execute=True 执行。
```

### 下推销售出库单
```
写入操作预览
操作类型: 下推
FormId: SAL_SaleOrder
组织: 01
参数:
- 源单: 销售订单 SAL00001
- 目标: 销售出库单
- 内容: 客户=某某公司, 物料=物料A, 数量=100
执行要求: 仅在用户明确确认后，使用相同工具并设置 execute=True 执行。
```
