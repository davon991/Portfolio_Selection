# spec.md (Freeze-0)
# Project: CtR 主目标 + CtB 风控约束（band）
# Data: Broad-asset-class ETFs
# Status: FROZEN

## 0. 范围与原则
- 决策变量唯一：价值权重向量 x。
- 风险输入唯一：收益协方差矩阵 V_t（滚动估计）。
- 指标口径唯一：CtR、CtB、D_R、D_B（见第3节）。
- 主模型唯一：CtR 主目标 + CtB 上界约束（band）（见第4节）。
- 主文 long-only；允许做空仅作为附录扩展，不进入主线与主实证。

## 1. 记号（唯一版本）
- 资产数量：n；资产索引 i=1,...,n。
- 价格：S_i(t)，使用“复权收盘价/Adjusted Close”。
- 简单收益：ξ_i(t) = S_i(t)/S_i(t-1) - 1。
- 收益向量：ξ(t) = (ξ_1(t),...,ξ_n(t))^T。
- 权重（决策变量）：x(t) = (x_1(t),...,x_n(t))^T。
- 预算约束：1^T x(t) = 1。
- 可行域（约束集合）：
  W = { x ∈ R^n : 1^T x = 1, 0 ≤ x_i ≤ x_max }。
- 协方差矩阵（滚动估计）：V_t = Cov_t(ξ)，正定/半正定，按估计器给出。
- 单资产波动：σ_i(t) = sqrt((V_t)_{ii})。
- 组合波动：σ_p(x; t) = sqrt(x^T V_t x)。

## 2. 回测时间结构（唯一口径）
- 观测频率：日度。
- 重平衡频率：月度（每月最后一个交易日）。
- 估计窗口：长度 L（见 calibration_protocol.md），用于估计 V_t。
- 时间一致性：
  - 在重平衡日 t_k：仅使用 {ξ(t_k-L),...,ξ(t_k-1)} 估计 V_{t_k}；
  - 在 t_k 生成 x(t_k)；
  - 持有区间收益从 (t_k → t_k+1) 开始记账；禁止任何前视使用。

## 3. 指标体系（唯一定义）
### 3.1 CtR（Contribution to Risk）
定义（归一化风险贡献）：
CtR_i(x; t) = x_i * (V_t x)_i / (x^T V_t x)
并满足 Σ_i CtR_i = 1。

风险预算向量：
b = (b_1,...,b_n)^T，b_i > 0，Σ_i b_i = 1。
ERC：b_i = 1/n。

CtR 偏离度（主目标指标）：
D_R(x; b, t) = Σ_{i=1}^n ( CtR_i(x; t) - b_i )^2。

### 3.2 CtB（Correlation to Basket）
定义（资产与组合收益的相关暴露）：
CtB_i(x; t) = Corr(ξ_i, ξ_p) = (V_t x)_i / ( σ_i(t) * σ_p(x; t) )，
其中 ξ_p = x^T ξ。

CtB 截面均值：
\overline{CtB}(x; t) = (1/n) Σ_i CtB_i(x; t)。

CtB 离散度（风控指标，主线唯一）：
D_B(x; t) = Σ_{i=1}^n ( CtB_i(x; t) - \overline{CtB}(x; t) )^2。

### 3.3 CtR–CtB 结构关系（用于解释，不作为额外约束）
CtR_i(x; t) = [ x_i * σ_i(t) / σ_p(x; t) ] * CtB_i(x; t)。

## 4. 主模型（唯一）
在每个重平衡时点 t_k，求解：
min_{x ∈ W}  D_R(x; b, t_k) + η ||x - x(t_{k-1})||_2^2 + γ ||x||_2^2
s.t.         D_B(x; t_k) ≤ δ

参数：
- δ：CtB 风控阈值（由 calibration_protocol.md 规则化构造与选择）
- η：平滑参数（由 turnover/成本约束校准）
- γ：稳定正则（尺度规则 + 敏感性口径）
- x(t_{k-1})：上一期实际持有权重；首期初始化按 calibration_protocol.md 规定。

实现等价形式（仅用于求解器；不改变模型口径）：
采用带容忍带的罚函数（hinge penalty）：
min_{x ∈ W}  D_R + η||x-x_prev||^2 + γ||x||^2 + (ρ/2) * (D_B - δ)_+^2
其中 (u)_+ = max(u, 0)，ρ>0 为罚强度（实现细节在代码中固定，主文不引入新的模型自由度）。

## 5. 基准策略（固定集合）
- EW：x_i = 1/n。
- GMV：min_{x ∈ W} x^T V_t x。
- ERC：min_{x ∈ W} D_R(x; (1/n)1, t)（与主模型同一 W 与同一 V_t）。

## 6. 交易与成本口径（唯一）
- 单期换手（重平衡 t_k）：
TO(t_k) = 0.5 * Σ_i | x_i(t_k) - x_i(t_{k-1}) |。
- 成本调整（比例成本）：
持有区间内净收益：ξ_p^net(t) = ξ_p(t) - c * TO(t_k)，t ∈ [t_k, t_{k+1})。
- 成本参数 c 由配置指定；主文报告主设定与附录成本敏感性。

## 7. 输出口径（与代码 I/O 契约一致）
每次 run 输出 results/<run_id>/，必须包含：
- run_manifest.json（spec版本、data哈希、代码版本、输出清单）
- diagnostics.json（数据与回测诊断）
- analysis_pack.json（关键统计摘要）
- panel.parquet（长表：date-asset 面板，含 weight/ctr/ctb/dr/db/delta/active/turnover 等）
- summary_metrics.csv、dr_db.csv、perf_daily.csv
- 论文图（pdf/png）：净值、回撤、CtR/CtB 分解、D_B vs δ 时序、（可选）D_R–D_B 前沿图

## 8. 版本与冻结
- spec.md 为 Freeze-0 文件，任何修改必须先提交 spec_diff.md，说明变更内容与影响面，并通过 smoke 运行。
