---
name: kingdee-query-guide
description: 金蝶云星空数据查询技巧指南（基于真实数据库元数据）
metadata:
  type: knowledge
  version: "3.0"
---

# 金蝶云星空数据查询技巧

## 查询工具

| 工具 | 用途 | 必填参数 |
|------|------|----------|
| `kingdee_query_bill` | 查询单据列表（ExecuteBillQuery） | form_id, field_keys, org_id |
| `kingdee_view_bill` | 查看单据详情（View） | form_id, org_id, number/bill_id |
| `kingdee_get_report` | 查询标准报表（余额表、利润表等） | form_id, org_id |
| `kingdee_get_kds_report` | 查询合并报表（合并报表、汇总报表、工作底稿等） | report_type, report_number, acct_system_number, acct_policy_number, currency_number, curr_unit_number, cycle_type, year, period |
| `kingdee_product_qa` | 金蝶产品智能问答 | question |
| `kingdee_query_metadata` | 查询字段定义 | form_id |
| `kingdee_search_form` | 搜索表单 | keyword |
| `kingdee_list_digest_templates` | 列出高管报表摘要模板 | 无（可选 template_id） |

**重要区分：** `kingdee_query_bill` 是查询接口（ExecuteBillQuery），`kingdee_view_bill` 是查看接口（View）。查询用 query，查看详情用 view。

## 接口参数说明

查询接口只包含一个 JSON 格式数据包参数，数据包包含具体的参数。

## 表单标识规则（FormId）

FormId 由前缀+业务名组成，前缀对应业务域：

| 域 | 前缀 | 示例表单 |
|----|------|----------|
| 财务 | GL_, AR_, AP_, FA_, IV_, ER_ | GL_Voucher（凭证）, AR_Receivable（应收单）, AP_Payable（应付单） |
| 销售 | SAL_, CRM_, DRP_, CMK_ | SAL_SaleOrder（销售订单）, SAL_SaleOutStock（销售出库单） |
| 采购 | PUR_, SCP_, SVM_ | PUR_PurchaseOrder（采购订单）, PUR_Requisition（请购单） |
| 库存 | STK_, QM_ | STK_InStock（入库单）, STK_InventoryBalance（即时库存） |
| 生产 | PRD_, MFG_, PLN_, SFC_, SUB_ | PRD_MolBill（生产订单）, MFG_BOM（BOM） |
| 基础 | BD_, BOS_, ORG_ | BD_Material（物料）, BD_Customer（客户）, BD_Supplier（供应商） |

## 字段引用语法

### 基础资料名称和编码
- 名称：基础资料key + `.FName`，示例：`FMaterialId.FName`（物料名称）
- 编码：基础资料key + `.FNumber`，示例：`FMaterialId.FNumber`（物料编码）

### 特殊基础资料编码/名称/内码
- **员工编码**用 `FStaffNumber`（不是 FNumber）
- **辅助属性名称**用 `FDataValue`（不是 FName）
- **组织内码**用 `FOrgId`（不是 FId）
- **用户内码**用 `FUserId`（不是 FId）

### 单据体内码
- 格式：单据体key + `_` + 分录主键
- 示例：`FEntity_FEntryId`

### 分录序号
- 格式：单据体key + `FSeq`
- 示例：`FEntity_FSeq`

### 弹性域维度查询（核算维度、辅助属性、仓位、职位等级）
- 内码：字段key + `.维度`，示例：`FAuxPropId.FFl00002`
- 名称（辅助属性）：字段key + `.维度.FDataValue`，示例：`FAuxPropId.FFl00002.FDataValue`
- 名称（核算维度）：字段key + `.维度.FName`，示例：`FAuxPropId.FFl00002.FName`

### 限制
- **多选基础资料**：不支持查询
- **查询不支持去重**

## 查询过滤（FilterString）

FilterString 跟 SQL 的 WHERE 条件一样：

```
FCreateDate>'2020-04-01' and (FMaterialId.FCreateOrgId.Id=100004 or FMaterialId.FCreateOrgId='机加事业部')
```

常用示例：
- 日期：`FDate >= '2026-01-01' and FDate <= '2026-12-31'`
- 状态：`FDocumentStatus = 'C'`（A=创建, B=审核中, C=已审核）
- 组合：`FCustId.FName = '某某公司' and FDate >= '2026-01-01'`
- 组织：`FOrgId.FNumber = '01'`（由权限系统自动注入）

## 分页查询

### 参数设置
- 每页行数：`Limit` 参数
- 开始行索引：`StartRow` 参数
- 分页时最好有确定的顺序，用 `OrderString` 排序

### 查询总数
- **总单据数**：`FieldKeys: "count(1)"`, `FilterString: "FID>0"`, `Limit: 0`
- **总行数**：`FieldKeys: "count(1)"`, `FilterString: "FID>0 and FEntity_FEntryId"`, `Limit: 0`
- **特别注意**：查询总数时 `Limit` 一定要设置为 0

### 分页循环
假设每页 10 行：
- 第一页：`Limit: 10, StartRow: 0`
- 第二页：`Limit: 10, StartRow: 10`
- 第三页：`Limit: 10, StartRow: 20`
- 以此类推...

## 常用查询示例

### 查询销售订单
```
工具: kingdee_query_bill
参数:
  org_id: "01"
  form_id: SAL_SaleOrder
  field_keys: FBillNo,FDate,FCustId.FName,FSalerId.FName,FDocumentStatus
  filter_string: FDate >= '2026-01-01'
  limit: 50
```

### 查询应收单
```
工具: kingdee_query_bill
参数:
  org_id: "01"
  form_id: AR_Receivable
  field_keys: FBillNo,FDate,FCUSTOMERID,FSALEORGID,FDocumentStatus
  filter_string: FDate >= '2026-01-01'
```

### 查询采购订单
```
工具: kingdee_query_bill
参数:
  org_id: "01"
  form_id: PUR_PurchaseOrder
  field_keys: FBillNo,FDate,FSupplierId.FName,FDocumentStatus
  filter_string: FDate >= '2026-01-01'
```

### 查询即时库存
```
工具: kingdee_query_bill
参数:
  org_id: "01"
  form_id: STK_InventoryBalance
  field_keys: FMaterialId.FName,FStockId.FName,FBaseQty
  filter_string: FStockId.FName = '成品仓'
```

### 分页查询示例
```
工具: kingdee_query_bill
参数:
  org_id: "01"
  form_id: SAL_SaleOrder
  field_keys: FBillNo,FDate,FCustId.FName,FDocumentStatus
  filter_string: FDate >= '2026-01-01'
  order_string: FDate DESC
  limit: 10
  start_row: 0
```

### 查询总数
```
工具: kingdee_query_bill
参数:
  org_id: "01"
  form_id: SAL_SaleOrder
  field_keys: "count(1)"
  filter_string: "FID>0"
  limit: 0
```

### 查看销售订单详情
```
工具: kingdee_view_bill
参数:
  org_id: "01"
  form_id: SAL_SaleOrder
  number: "SAL00001"
```

### 查询表单字段定义
```
工具: kingdee_query_metadata
参数:
  form_id: SAL_SaleOrder
```

## 报表查询（kingdee_get_report）

报表分两种类型，参数不同：

### 简单账表（标准报表）

适用于利润表、资产负债表、科目余额表等。通过 `field_keys` 指定字段，`Model` 传入过滤参数。

```
工具: kingdee_get_report
参数:
  org_id: "01"
  form_id: GLR_ProfitStatement
  field_keys: "FAccountId.FNumber,FAccountId.FName,FDebit,FCredit"
  scheme_id: ""
  start_row: 0
  limit: 2000
```

### 分页账表（明细报表）

适用于存货收发存汇总表、物料收发明细等。通过 `scheme_id` 指定过滤方案，`quickly_conditions` 传入快速过滤条件。

过滤方案ID可通过SQL查询：`SELECT FSCHEMEID, FSCHEMENAME FROM T_BAS_FILTERSCHEME WHERE FFORMID='报表FormId'`

```
工具: kingdee_get_report
参数:
  org_id: "01"
  form_id: STK_StockDetailRpt
  scheme_id: "5fb2412a4f22a3"
  quickly_conditions: '[{"FieldName":"BeginMaterialId","FieldValue":"041602"},{"FieldName":"EndMaterialId","FieldValue":"041602"},{"FieldName":"BeginDate","FieldValue":"2026-01-01"},{"FieldName":"EndDate","FieldValue":"2026-12-31"}]'
```

**注意：** 报表查询比较耗时，注意查询时间范围和调用频率。

## 合并报表查询（kingdee_get_kds_report）

用于查询合并报表系统（KDS）的报表，包括合并报表、汇总报表、工作底稿、抵消表、阿米巴报表、预算报表等。

### 报表类型

| 类型代码 | 类型名称 | 说明 |
|---------|---------|------|
| 1 | 个别报表 | 不同模板同一期间构成 |
| 2 | 穿透报表 | 同一模板多个期间 |
| 14 | 汇总报表 | - |
| 15 | 合并报表 | - |
| 16 | 工作底稿 | - |
| 17 | 合并个别报表 | - |
| 20 | 个别报表调整表 | - |
| 31 | 抵消表 | - |
| 51 | 阿米巴报表 | - |
| 61 | 预算报表 | - |

### 周期类型

| 周期代码 | 周期名称 | 说明 |
|---------|---------|------|
| 1 | 会计期间 | - |
| 2 | 日报 | - |
| 3 | 周报 | - |
| 4 | 月报 | - |
| 5 | 季报 | - |
| 6 | 半年报 | - |
| 7 | 年报 | - |
| 8 | 旬报 | - |
| 10 | 自定义 | - |

### 使用示例

**查询合并报表：**
```
工具: kingdee_get_kds_report
参数:
  report_type: 15
  report_number: "HB00001"
  acct_system_number: "KJHSTX01_SYS"
  acct_policy_number: "KJZC01_SYS"
  currency_number: "PRE001"
  curr_unit_number: "JEDW01_SYS"
  cycle_type: 4
  year: 2025
  period: 3
  org_number: "0581"
  scope_type_number: "HXX001"
  scope_number: "001"
```

**查询汇总报表：**
```
工具: kingdee_get_kds_report
参数:
  report_type: 14
  report_number: "HZ00001"
  acct_system_number: "KJHSTX01_SYS"
  acct_policy_number: "KJZC01_SYS"
  currency_number: "PRE001"
  curr_unit_number: "JEDW01_SYS"
  cycle_type: 4
  year: 2025
  period: 3
```

**注意：** 不同报表类型所需参数可能不同，部分报表需要 org_number、scope_type_number、scope_number 参数。

## 产品智能问答（kingdee_product_qa）

用于解答金蝶产品使用问题，调用金蝶云社区智能搜索接口。
产品 ID 从连接配置中读取，无需每次传入。

### 使用示例

**基本问答：**
```
工具: kingdee_product_qa
参数:
  question: "总账怎么初始化？"
```

**多轮对话：**
```
工具: kingdee_product_qa
参数:
  question: "凭证怎么审核？"
  session_id: "833052315488370176"
```

**注意：** 首次使用需要在连接配置中填写：
- 金蝶云社区 Token（kdcloud_token）
- 金蝶产品（kdcloud_product_id）

## 工作流审批（kingdee_workflow_audit）

当单据配置了工作流时，使用此接口进行审批（而非 kingdee_audit_bill）。

```
工具: kingdee_workflow_audit
参数:
  org_id: "01"
  form_id: PUR_PurchaseOrder
  numbers: ["CGDD000695"]
  user_id: 100008
  approval_type: 1
```

approval_type: 1=审批通过, 2=驳回, 3=终止

## 状态码

| 字段 | 值 | 含义 |
|------|---|------|
| FDocumentStatus | A | 创建中 |
| FDocumentStatus | B | 审核中 |
| FDocumentStatus | C | 已审核 |
| FDocumentStatus | D | 重新审核 |
| FClosedStatus | A | 未关闭 |
| FClosedStatus | B | 已关闭 |
