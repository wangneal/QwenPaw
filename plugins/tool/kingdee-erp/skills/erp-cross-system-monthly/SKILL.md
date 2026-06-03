---
name: erp-cross-system-monthly
description: 跨ERP系统月度报表 - 汇编多系统月度经营数据生成综合月报
metadata:
  type: knowledge
  version: "1.0"
---

# 跨ERP系统月度报表

## 月报场景

综合月度经营报表汇集多个ERP系统的关键数据，形成管理层全景视图：
- **收入与成本**：各系统销售数据汇总，计算综合毛利
- **应收与应付**：跨系统应收应付余额汇总，掌握资金状况
- **库存价值**：多系统库存数据合并，了解整体库存水平
- **现金流**：结合各系统收付款数据，分析现金流入流出

## 涉及工具

- `erp_unified_query`：多系统并行查询通用业务数据
- `kingdee_get_report`：获取金蝶标准财务报表（利润表、资产负债表等）
- `kingdee_query_bill`：查询金蝶特定业务单据明细

## 月报编制步骤

1. **确定月度范围**：指定年月，如 2024年12月
2. **分系统查询关键指标**：金蝶查财务报表和库存，SAP查销售和采购（待后端实现），用友查辅助核算（待后端实现）
3. **汇编数据**：将各系统结果整理到统一报表格式
4. **计算综合指标**：毛利、周转率、同比环比等

## 月报查询示例

### 财务指标（金蝶利润表/资产负债表）
```
工具: kingdee_get_report
参数:
  report_id: GLR_ProfitStatement
  filter: FYear = 2024 and FPeriodNumber = 12
```

### 销售指标（多系统销售订单汇总）
```
工具: erp_unified_query
参数:
  systems: kingdee,sap
  query_params: {"form_id":"SAL_SaleOrder","field_keys":"FBillNo,FDate,FCustId.FName,FQty,FAmount","filter":"FDate>='2024-12-01' and FDate<='2024-12-31'"}
  limit: 100
```

### 库存指标（金蝶库存余额）
```
工具: kingdee_query_bill
参数:
  form_id: STK_InventoryBalance
  field_keys: FMaterialId.FName,FStockId.FName,FBaseQty,FUnitId.FName
  filter_string: FStockId.FName = '成品仓'
  limit: 100
```

## 月报模板结构

| 板块 | 数据来源 | 关键指标 |
|------|----------|----------|
| 营业收入 | 金蝶+SAP | 销售订单金额汇总 |
| 营业成本 | 金蝶+SAP | 出库成本汇总 |
| 毛利 | 计算得出 | 收入-成本 |
| 应收余额 | 金蝶+SAP | 期末应收总额 |
| 应付余额 | 金蝶+SAP | 期末应付总额 |
| 库存余额 | 金蝶+SAP | 期末库存价值 |
| 现金流入/流出 | 金蝶 | 收付款单汇总 |

## 注意事项

- **币别统一**：跨系统数据需统一币别换算基准，建议以人民币为基准
- **期间口径**：确保各系统查询的会计期间一致
- **数据时效**：查询时注意各系统数据的更新频率，部分系统可能存在延迟
- **当前限制**：目前只有金蝶后端已实现，其他系统数据待后端开发后才能获取
