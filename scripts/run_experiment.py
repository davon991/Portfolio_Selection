import argparse
import platform
import sys
from pathlib import Path
from datetime import datetime, timezone

# ===== FIX: ensure project root is on sys.path so `import src...` works =====
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../scripts/ -> project root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# ==========================================================================

from src.utils import (
    load_yaml,
    ensure_dir,
    compute_run_id,
    read_version_from_frozen_doc,
    sha256_file,
    save_json,
)
from src.data_prep import prepare_returns
from src.backtest import run_full_pipeline
from src.reporting import make_all_figures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=str)
    args = parser.parse_args()

    cfg = load_yaml(args.config)

    results_root = Path(cfg["run"]["results_dir"])
    ensure_dir(results_root)

    # Compute run_id
    run_id = compute_run_id(cfg)
    run_dir = results_root / run_id
    ensure_dir(run_dir)

    # Freeze doc versions (must exist in repo)
    spec_path = Path("paper/spec.md")
    dc_path = Path("data/data_contract.md")
    cal_path = Path("paper/calibration_protocol.md")

    spec_version = read_version_from_frozen_doc(spec_path)
    data_contract_version = read_version_from_frozen_doc(dc_path)
    calibration_protocol_version = read_version_from_frozen_doc(cal_path)

    # Prepare returns (processed artifacts go to data/processed)
    data_artifacts = prepare_returns(cfg)

    # Run full pipeline (calibration + backtests + outputs)
    outputs = run_full_pipeline(cfg, run_dir, data_artifacts)

    # Figures
    if cfg.get("reporting", {}).get("make_figures", True):
        make_all_figures(cfg, run_dir)

    # Build run_manifest.json (per spec.md schema)
    run_manifest = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "spec_version": spec_version,
        "data_contract_version": data_contract_version,
        "calibration_protocol_version": calibration_protocol_version,
        "code_commit": cfg["run"].get("code_commit", "NA"),
        "python_version": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "universe": cfg["data"]["tickers"],
        "date_range": {"start": cfg["data"]["start"], "end": cfg["data"]["end"]},
        "frequency": {"data": "daily", "rebalance": "monthly"},
        "window_L": int(cfg["experiment"]["window_L"]),
        "covariance_method": cfg["experiment"]["covariance_method"],
        "constraints": {"x_max": float(cfg["experiment"]["x_max"])},
        "costs": {"c": float(cfg["experiment"]["cost_c"])},
        "parameters": {
            "delta": outputs["final_parameters"]["delta"],
            "eta": outputs["final_parameters"]["eta"],
            "gamma": outputs["final_parameters"]["gamma"],
            "rho": float(cfg["solver"]["rho"]),
            "eps_db": float(cfg["experiment"]["eps_db"]),
        },
        "data_hashes": {
            "returns_parquet": sha256_file(Path(data_artifacts["returns_parquet"])),
            "aligned_calendar": sha256_file(Path(data_artifacts["aligned_calendar_csv"])),
        },
        "outputs": outputs["written_files"],
    }
    save_json(run_dir / "run_manifest.json", run_manifest)

    # Save config.json (expanded)
    save_json(run_dir / "config.json", cfg)


if __name__ == "__main__":
    main()
