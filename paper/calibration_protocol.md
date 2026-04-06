# calibration_protocol.md (Freeze-2)
# Calibration Protocol for (δ, η, γ) and acceptance criteria
# Status: FROZEN

## 0. 目的
在固定 spec.md 与 data_contract.md 的前提下，给出 (δ, η, γ) 的规则化校准协议：
- 可复现
- 低自由度
- 可审计（run_manifest.json + analysis_pack.json）

## 1. 数据划分（固定规则）
以重平衡序列 {t_1,...,t_K} 为单位划分：
- Train: 前 60% 的重平衡点
- Val:   中间 20%
- Test:  后 20%

约束：
- Train 与 Val 均需包含足够多的重平衡点（建议 ≥ 24 个月）；不足则改为“固定日期切分”，并记录到 run_manifest.json。

## 2. δ：CtB 阈值构造与选择（核心）
### 2.1 训练期基准分布构造
对每个 t_k ∈ Train：
1) 估计 V_{t_k}（按 spec 主设定）
2) 求 ERC：
   x^{ERC}(t_k) ∈ argmin_{x∈W} D_R(x; b=1/n)
3) 计算 z_k = D_B(x^{ERC}(t_k))

得到经验分布 {z_k}。

### 2.2 阈值族（低自由度）
固定分位数集合：
P = {0.4, 0.5, 0.6, 0.7, 0.8}

定义：
δ(p) = Quantile_p({z_k}),  p ∈ P

### 2.3 验证期选择
对每个候选 p ∈ P：
- 固定 δ = δ(p)
- 采用后述 η 校准规则得到 η(p)
- 固定 γ（第4节）
- 在 Val 上运行主模型，计算 Val 目标函数（用于比较）：
  Score(p) = Sharpe_net(p) - λ_TO * avg_TO(p) - λ_DD * MDD(p)

其中：
- Sharpe_net 为成本后 Sharpe
- avg_TO 为平均换手
- MDD 为最大回撤
- λ_TO, λ_DD 为预先固定常数（写入 config，不在校准中调整）
选择：
p* = argmax_p Score(p)
并固定 δ = δ(p*) 进入 Test。

### 2.4 可行性下界检查（实现级）
在 Train∪Val 上，额外求解：
x^{Bmin}(t_k) ∈ argmin_{x∈W} D_B(x; t_k)
m_k = D_B(x^{Bmin}(t_k))
必要条件：δ ≥ max m_k
若 δ(p*) 不满足，则选取满足可行性的最小更大分位数，或将该 run 标记为“不可接受”（见第5节拒绝标准）。

## 3. η：以交易可执行性为准则的单调校准
### 3.1 目标
在 Val 上满足：
avg_TO(η) ≤ TO_target
其中 TO_target 固定写入 config（建议主设定 0.20/月，稳健性 0.10 与 0.30 作为附录）。

### 3.2 搜索方法
利用 η 与 avg_TO 的单调性，采用二分搜索：
- 给定区间 [η_low, η_high]（写入 config）
- 迭代直至 |avg_TO - TO_target| ≤ tol 或达到 max_iter
得到 η*。

说明：
- η 的校准不以收益指标直接优化；收益仅用于 δ 的候选比较（Score）。

## 4. γ：尺度规则 + 最小稳定原则
定义尺度：
s_t = tr(V_{t_k}) / n

固定候选集合：
α ∈ {1e-6, 1e-5, 1e-4}
取：
γ = α * median_{t_k ∈ Train} s_t

选择规则：
- 取“最小且满足数值稳定”的 α（收敛失败率为 0，或低于阈值），并固定进入 Test。
- γ 不在 Test 上再调整；仅在附录报告敏感性（α 网格）。

## 5. 拒绝标准（自动化；写入 diagnostics.json）
若满足任一条件，则该配置（或该 δ 候选）视为不可接受：
1) 约束激活率极端（Val 或 Test）：
   activation_rate < 0.05 或 > 0.90
2) 贴边率极端（长期大量 x_i=0 或 x_i=x_max）：
   boundary_share > 0.80（阈值写入 config）
3) 求解失败或不收敛：
   fail_rate > 0.00（主线要求 0；允许在附录给出放宽口径）
4) 可行性失败：
   存在 t_k 使得 D_B 最小值 m_k > δ（见 2.4）
5) 换手异常：
   avg_TO 超过上限 TO_cap（写入 config）

拒绝信息与触发期列表必须记录到 diagnostics.json 与 run_manifest.json。

## 6. 输出要求（用于论文与 GPT 二次分析）
每个 run 必须生成：
- analysis_pack.json：δ/η/γ、激活率、贴边率、D_B 降幅、D_R 变化、成本后指标变化、异常期列表
- dr_db.csv：逐期记录 D_R, D_B, δ, active, turnover
- summary_metrics.csv：策略对照汇总
- run_manifest.json：记录上述文件哈希与 spec/contract/protocol 版本号
