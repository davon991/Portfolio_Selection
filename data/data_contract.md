# data_contract.md (Freeze-1)
# Data Contract: Broad-asset-class ETFs
# Status: FROZEN

## 0. 数据集目标
构建日度复权价格与收益面板，用于月度重平衡、滚动协方差估计与组合回测。

## 1. 资产范围（主设定）
主实证使用大类资产 ETF（示例集合，可替换但需保持“跨资产类别覆盖”）：
- Equity US: SPY (or VTI)
- Equity Dev ex-US: EFA
- Equity EM: EEM
- UST 7-10Y: IEF
- UST 20+Y: TLT
- IG Credit: LQD
- HY Credit: HYG
- Gold: GLD
- Broad Commodities: PDBC (or DBC)
- REITs: VNQ

约束：资产数量 n 建议 8–12；最终资产列表写入 data/processed/assets.json，并在 run_manifest.json 记录。

## 2. 原始字段（raw 层）
每条记录至少包含：
- date: YYYY-MM-DD（交易日）
- asset: string（ticker）
- adj_close: float（复权收盘价；若仅 close，则必须在 raw 元数据中说明复权方式）

可选字段：
- close, volume（不进入主线计算，仅用于检查）

## 3. 处理规则（processed 层）
### 3.1 交易日对齐
- 基准日历：以“所有资产交易日交集”为默认（intersection calendar）。
- 若采用并集（union）则必须在 spec_diff.md 中说明，并在 diagnostics.json 报告缺失填补策略；主线默认禁止对收益做插值。

### 3.2 缺失处理
- 若某资产在日期 t 缺失价格，则该日期在 intersection 日历下被剔除。
- 资产起始/终止日期差异导致的样本缩短必须在 assets.json 中记录（start_date/end_date/coverage）。
- 主线不对收益率 ξ_i(t) 做前向填充或插值。

### 3.3 收益计算（唯一口径）
对每个资产 i：
- 价格序列为 adj_close。
- 简单收益：
  ξ_i(t) = adj_close_i(t) / adj_close_i(t-1) - 1
- 输出长表 returns：
  columns = [date, asset, ret]（ret 为 float）

## 4. 输出文件（processed 层）
必须生成：
- data/processed/returns.parquet（长表：date, asset, ret）
- data/processed/returns.csv（同口径导出）
- data/processed/assets.json（每个资产：ticker, category, start_date, end_date, missing_rate, notes）
- data/processed/calendar.json（交易日列表；用于回测一致性）

## 5. 数据质量诊断（写入 diagnostics.json 的 data 部分）
- 每资产缺失率与覆盖区间
- 每日可用资产数分布（intersection 下应恒为 n）
- 极端收益统计（分位数/最大值；不在主线自动处理）
- 时间一致性检查：收益是否严格由 t 与 t-1 计算；不存在未来数据引用

## 6. 变更与冻结
- data_contract.md 为 Freeze-1 文件。
- 更换资产列表或对齐/缺失规则属于“契约变更”，必须走 spec_diff.md，并重新生成 data 哈希写入 run_manifest.json。
