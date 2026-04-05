# paper/spec.md
# CtR 主目标 + CtB 风控约束（band）项目规范（最终固定版）

> 本文件为全项目唯一规范：符号体系、指标定义、模型、校准协议、回测口径与输出格式均以此为准。
> 论文正文与代码实现不得引入替代符号或并行口径。

---

## 0. 研究对象与基本设定

- 资产集合：i = 1,...,n
- 频率：日频数据（daily）
- 重平衡：月度（month-end 或月初第一个交易日，二者择一并固定）
- 风险输入：收益率协方差矩阵 V_t（rolling window 估计）
- 决策变量：价值权重向量 x(t) ∈ R^n
- 主文默认：long-only + 权重上限（可交易性与可解释性优先）

---

## 1. 符号体系（全篇固定）

### 1.1 数据与收益
- 价格：S_i(t)
- 简单收益率：ξ_i(t) = (S_i(t+1) - S_i(t)) / S_i(t)
- 收益向量：ξ(t) = (ξ_1(t),...,ξ_n(t))^T

### 1.2 权重与组合收益
- 权重向量：x(t) = (x_1(t),...,x_n(t))^T
- 预算约束：1^T x(t) = 1
- 组合收益：ξ_p(t) = x(t)^T ξ(t)

### 1.3 风险输入与波动
- 协方差矩阵：V_t = Cov_t(ξ) ∈ R^{n×n}
- 单资产波动：σ_i(t) = sqrt((V_t)_{ii})
- 组合波动：σ_p(x; V_t) = sqrt(x^T V_t x)

---

## 2. 约束集合（主文固定）

可行域（主设定）：
W = { x ∈ R^n : 1^T x = 1, 0 ≤ x_i ≤ x_max }

- x_max 为权重上限（主设定固定一个值；稳健性检验再变动）
- 做空/其他线性约束（行业/组别/风险因子暴露）仅允许放入附录扩展，不进入主线模型

---

## 3. 指标体系（全篇固定）

### 3.1 CtR：Contribution to Risk（风险贡献）
定义（归一化风险贡献）：
CtR_i(x) = x_i (V_t x)_i / (x^T V_t x)

性质：
Σ_i CtR_i(x) = 1

风险预算（budget）向量：b = (b_1,...,b_n)^T，b_i>0, Σ_i b_i = 1
ERC 为 b_i = 1/n

主目标偏离度（固定）：
D_R(x; b) = Σ_i (CtR_i(x) - b_i)^2

### 3.2 CtB：Correlation-to-Basket（相关暴露）
组合与资产的相关系数：
CtB_i(x) = Corr(ξ_i, ξ_p) = (V_t x)_i / (σ_i σ_p(x;V_t))

截面均值：
CtB_bar(x) = (1/n) Σ_i CtB_i(x)

离散度（固定，主文唯一 CtB 风控量）：
D_B(x) = Σ_i (CtB_i(x) - CtB_bar(x))^2

（可选诊断量，仅用于附录或图注，不进入模型）
D_B_max(x) = max_i |CtB_i(x) - CtB_bar(x)|

### 3.3 CtR–CtB 关系式（用于解释，不作为额外约束）
CtR_i(x) = (x_i σ_i / σ_p(x;V_t)) * CtB_i(x)

---

## 4. 基准策略（用于校准与对照）

- EW：x_i = 1/n
- GMV：min_{x∈W} x^T V_t x
- ERC（CtR-only）：min_{x∈W} D_R(x; (1/n)1)

---

## 5. 主模型（全文唯一主模型）

在每个重平衡时点 t_k，给定 V_{t_k} 与上一期权重 x_{t_{k-1}}，求解：

min_{x∈W}  D_R(x; b) + η ||x - x_prev||_2^2 + γ ||x||_2^2
s.t.        D_B(x) ≤ δ

其中：
- b：风险预算（主文默认 ERC：b_i=1/n；如需要可在附录扩展不同 b）
- δ：CtB 风控阈值（第6节给出校准协议）
- η：平滑项参数（用交易约束校准）
- γ：数值稳定正则（尺度规则给定）

约束处理（实现层）：
- 主线实现采用“容忍带/罚函数”或“增广拉格朗日”之一，二者等价且需在代码中固定默认实现。
- 主文不讨论实现细节；实现细节进入 src/ 与附录。

---

## 6. 参数校准协议（固定流程）

### 6.1 数据划分
- Train / Validation / Test 三段（或滚动校准—滚动测试，二者择一并固定）
- Test 期间参数不得再调整

### 6.2 δ（CtB 阈值）：基于 Train 期 ERC 的 D_B 分布
在 Train 期每个 t_k：
1) 求 ERC：x^{ERC}(t_k)
2) 记录 z_k = D_B(x^{ERC}(t_k))

给定分位数集合：
P = {0.4, 0.5, 0.6, 0.7, 0.8}

构造阈值族：
δ(p) = Quantile_p({z_k})

在 Validation 上选择 p*（离散选择）：
p* = argmax_{p∈P} Score_val(p)

Score_val(p) 的默认形式（固定）：
Score = Sharpe_net - λ_TO * avg_turnover
（λ_TO 为固定常数，或将 turnover 直接作为硬约束，两种方式择一并固定）

最终：δ = δ(p*)

### 6.3 η（平滑参数）：以目标换手率/成本预算校准
固定 δ 与 γ 后，用单调搜索（二分）确定 η，使 Validation 期满足：
avg_turnover(η) ≤ TO_target
其中 TO_target 在 spec 中固定（主文一个值；附录可报告敏感性）

### 6.4 γ（稳定正则）：尺度规则 + 敏感性报告
固定规则：
γ = α * tr(V_t)/n
α ∈ {1e-6, 1e-5, 1e-4}

选择最小且足以消除数值不稳定的 α 作为主设定；其余 α 的影响放附录。

---

## 7. 回测协议（固定口径）

### 7.1 滚动估计与重平衡
- 在每个 t_k 用过去 L 个交易日估计 V_{t_k}
- L 主设定：5 年（≈ 252*5）；稳健性：3 年、7 年
- 重平衡：月度（固定规则：月末/下月首个交易日）

### 7.2 换手率与成本
换手率：
TO_{t_k} = 0.5 * Σ_i |x_i(t_k) - x_i(t_{k-1})|

成本调整：
ξ_net(t) = ξ_gross(t) - c * TO_{t_k} ,  t∈[t_k, t_{k+1})
其中 c 为单边费率；主文固定一个主费率，附录给情景网格。

---

## 8. 结果输出规范（与 results/ 目录一致）

每次运行输出到 results/<run_id>/，其中 <run_id> = YYYYMMDD_HHMM_<hash>

必须产出：
- config.json（实验与模型配置）
- run_meta.json（数据区间、资产列表、样本量、版本、随机种子）
- weights.csv（date + n列权重）
- ctr.csv（date + n列 CtR_i）
- ctb.csv（date + n列 CtB_i）
- dr_db.csv（date, D_R, D_B, delta, constraint_active, turnover, penalty_value）
- perf_daily.csv（date, ret_gross, ret_net, 以及基准策略净收益列）
- summary_metrics.csv（年化收益/波动/Sharpe/MDD/换手/成本后指标）
- 关键图表（png/pdf）+ 对应的绘图数据 CSV（同名 *_data.csv）

图表必须与机器可读文件一一对应，以便后续自动分析与复现。

---
