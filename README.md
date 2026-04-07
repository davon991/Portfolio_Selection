# CtR 主目标 + CtB 风控约束（band）

本仓库实现并复现实验：在风险预算框架下，以 CtR 偏离度作为主目标，并对 CtB 离散度施加风控约束（band）。
所有符号、指标与输出契约由以下冻结文件唯一约束：

- paper/spec.md  (Freeze-0)
- data/data_contract.md  (Freeze-1)
- paper/calibration_protocol.md  (Freeze-2)

## 1. 安装
建议使用 Python 3.10+。
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
