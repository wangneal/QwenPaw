---
name: erp-cross-system-reconciliation
description: 跨ERP系统数据对账 - 比较金蝶与SAP/用友等系统的应收、应付、库存数据差异
metadata:
  type: knowledge
  version: "1.0"
---

# 跨ERP系统数据对账

## 对账场景

跨系统对账用于发现不同ERP系统间的数据差异，常见场景：
- **应收对账**：金蝶 vs SAP 的客户应收余额是否一致
- **应付对账**：金蝶 vs 用友的供应商应付余额是否一致
- **库存对账**：金蝶 vs SAP 的物料库存数量是否一致

## 核心工具

使用 `erp_compare_data` 工具进行两系统数据对比。

**工具签名：**
```
erp_compare_data(left_system, left_query, right_system, right_query, key_field, compare_fields="")
```

**参数说明：**
- `left_system`：左系统标识，如 `kingdee`、`sap`、`yonyou`
- `left_query`：左系统查询参数 JSON，包含 form_id、field_keys、filter
- `right_system`：右系统标识
- `right_query`：右系统查询参数 JSON
- `key_field`：匹配键字段名，如 `FNumber`、`FName`
- `compare_fields`：对比字段，如 `FRecAmount`、`FQty`，多个用逗号分隔

## 对账步骤

1. **确定对账目标**：明确比对应收、应付还是库存数据
2. **设计左右系统查询参数**：分别指定两个系统的表单、字段、过滤条件
3. **选择匹配键字段**：通常用编码（FNumber）或名称（FName）作为关联键
4. **执行对账**：调用 `erp_compare_data` 工具
5. **分析差异结果**：结果分三类，仅左系统有、仅右系统有、两系统都有但值不同

## 对账示例

### 金蝶 vs SAP 应收对账
```
工具: erp_compare_data
参数:
  left_system: kingdee
  left_query: {"form_id":"AR_Receivable","field_keys":"FNumber,FCustId.FName,FRecAmount","filter":"FDate>='2024-01-01'"}
  right_system: sap
  right_query: {"form_id":"AR","field_keys":"Number,CustomerName,Amount","filter":"Date>='2024-01-01'"}
  key_field: FNumber
  compare_fields: FRecAmount
```

### 金蝶 vs 用友 库存对账
```
工具: erp_compare_data
参数:
  left_system: kingdee
  left_query: {"form_id":"STK_InventoryBalance","field_keys":"FMaterialId.FNumber,FMaterialId.FName,FBaseQty","filter":"FStockId.FName='成品仓'"}
  right_system: yonyou
  right_query: {"form_id":"ST","field_keys":"InvCode,InvName,Quantity","filter":"WhName='成品仓'"}
  key_field: FMaterialId.FNumber
  compare_fields: FBaseQty
```

## 权限检查

调用 `erp_compare_data` 时会自动调用 `check_integration_permission` 检查两系统的读取权限。任一系统权限不足时将返回错误提示。

## 注意事项

- **编码映射**：不同系统的编码体系可能不同，需先确认匹配键能正确关联
- **币别统一**：金额对比前需确认币别一致，或在查询条件中统一换算基准
- **期间口径**：确保两边查询的日期范围一致
- **当前限制**：目前只有金蝶后端已实现，SAP/用友等后端待未来开发
