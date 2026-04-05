# Portfolio Selection: CtR Main Objective + CtB Risk-Control Band

本项目实现并复现实证研究：在风险预算（CtR / Risk Budgeting）框架下，将 CtB（Correlation-to-Basket）离散度作为风控约束（band），构造可复现的组合优化与滚动回测流程。

- 规范文件：`paper/spec.md`（符号、指标、模型、校准协议、回测口径、输出格式的唯一来源）
- 目标：同时输出论文图表与机器可读结果（CSV/JSON），便于进一步分析与写作。

---

## 1. 数据：大类 ETF（默认资产池）

默认资产池（可在 `src/config.py` 中修改）：

| Asset Class | Ticker | Notes |
|---|---|---|
| US Equity | SPY | S&P 500 |
| Developed ex-US Equity | EFA | MSCI EAFE |
| Emerging Markets Equity | EEM | MSCI EM |
| US Treasuries (7-10Y) | IEF | duration exposure |
| US Treasuries (20+Y) | TLT | duration exposure |
| US TIPS | TIP | inflation-linked |
| IG Credit | LQD | investment-grade corporate |
| HY Credit | HYG | high yield |
| Gold | GLD | defensive |
| Broad Commodities | DBC | commodity basket |
| US REITs | VNQ | real estate |

建议起始日期：2006-01-01（受 DBC 等 ETF 成立时间影响）。实际起始日期会在下载后由“全资产共同可用区间”自动裁剪。

---

## 2. 环境与依赖

建议 Python 3.10+。

核心依赖：
- numpy, pandas
- scipy
- scikit-learn（Ledoit-Wolf shrinkage）
- yfinance（下载 ETF Adjusted Close）
- matplotlib（绘图）

安装：
```bash
pip install -r requirements.txt
