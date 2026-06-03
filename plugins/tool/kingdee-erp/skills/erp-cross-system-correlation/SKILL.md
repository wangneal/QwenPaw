---
name: erp-cross-system-correlation
description: 跨ERP系统关联查询 - 跟踪业务链路跨越多个系统（如金蝶订单→SAP出货→用友收款）
metadata:
  type: knowledge
  version: "1.0"
---

# 跨ERP系统关联查询

## 关联查询场景

当一笔业务跨越多个ERP系统时，需要关联查询来追踪完整链路：
- **订单→出货→收款**：金蝶下销售订单，SAP执行出库，用友收款核销
- **采购申请→采购订单→入库**：金蝶采购申请，SAP采购订单，金蝶入库确认
- **多系统客户余额汇总**：同一客户在金蝶和SAP都有应收记录

## 核心工具

使用 `erp_unified_query` 工具进行多系统并行查询。

**工具签名：**
```
erp_unified_query(systems, query_params, limit=100)
```

**参数说明：**
- `systems`：逗号分隔的系统标识，如 `kingdee,sap`、`kingdee,sap,yonyou`
- `query_params`：JSON 格式查询参数，包含 form_id、field_keys、filter
- `limit`：每个系统返回的最大记录数，默认100

## 关联查询步骤

1. **确定查询目标**：明确要追踪的业务链路和涉及的系统
2. **设计统一查询参数**：注意不同系统的表名和字段名可能不同，需设计兼容的查询
3. **执行查询**：调用 `erp_unified_query` 获取各系统结果
4. **关联分析**：根据关联键将各系统数据进行匹配和汇总

## 关联查询示例

### 多系统客户应收汇总
```
工具: erp_unified_query
参数:
  systems: kingdee,sap
  query_params: {"form_id":"AR_Receivable","field_keys":"FBillNo,FDate,FCustId.FName,FRecAmount","filter":"FCustId.FName='某某公司'"}
  limit: 50
```

### 跨系统销售订单追踪
```
工具: erp_unified_query
参数:
  systems: kingdee,sap
  query_params: {"form_id":"SAL_SaleOrder","field_keys":"FBillNo,FDate,FCustId.FName,FMaterialId.FName,FQty,FAmount","filter":"FDate>='2024-01-01'"}
  limit: 100
```

### 跨系统库存查询
```
工具: erp_unified_query
参数:
  systems: kingdee,sap,yonyou
  query_params: {"form_id":"STK_InventoryBalance","field_keys":"FMaterialId.FNumber,FMaterialId.FName,FBaseQty,FStockId.FName","filter":"FMaterialId.FName='原材料A'"}
  limit: 100
```

## 关联键设计

跨系统关联需要找到业务上的共同标识：
- **客户关联**：客户编码或客户名称（注意各系统命名可能不同）
- **物料关联**：物料编码（推荐统一编码体系）或物料名称
- **订单关联**：订单号（需确认各系统是否使用相同编号规则）
- **供应商关联**：供应商编码或名称

## 权限检查

调用 `erp_unified_query` 时会自动检查各系统的读取权限。权限不足的系统会被跳过并给出提示。

## 注意事项

- **字段映射**：不同系统相同业务含义的字段名可能不同，查询时需分别指定
- **数据去重**：同一客户在多系统可能有不同编码，关联时需注意
- **当前限制**：目前只有金蝶后端已实现，其他系统后端待开发后查询结果才会返回实际数据
