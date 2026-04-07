from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.utils import ensure_dir, save_json


@dataclass
class DataArtifacts:
    returns_parquet: str
    assets_json: str
    aligned_calendar_csv: str


def _set_yfinance_tz_cache_location(cache_dir: Path) -> None:
    """
    yfinance uses a sqlite tz-cache (tkr-tz.db). On Windows this can get locked.
    Force cache into project-local directory to reduce locking issues.
    """
    try:
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(str(cache_dir))
    except Exception:
        # Non-fatal; proceed without custom cache location
        pass


def _download_yfinance_adj_close(tickers: List[str], start: str, end: str, cache_dir: Path) -> pd.DataFrame:
    """
    Download adjusted price series using yfinance.
    We enforce threads=False to avoid sqlite "database is locked" from concurrent tz-cache writes.
    """
    _set_yfinance_tz_cache_location(cache_dir)

    df = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=True,   # adjusted prices
        progress=False,
        threads=False,      # IMPORTANT: avoid concurrent sqlite locks
        group_by="column",
    )

    # yfinance returns either:
    # - MultiIndex columns: (field, ticker) when multiple tickers
    # - Single-level columns when one ticker
    if df is None or len(df) == 0:
        raise RuntimeError("yfinance download returned empty dataframe. Check network or ticker symbols.")

    if isinstance(df.columns, pd.MultiIndex):
        # With auto_adjust=True, price field is typically "Close"
        if "Close" in df.columns.get_level_values(0):
            close = df["Close"].copy()
        else:
            # fallback: take first field
            first_field = df.columns.levels[0][0]
            close = df[first_field].copy()
    else:
        # single ticker
        if "Close" in df.columns:
            close = df[["Close"]].copy()
            close.columns = [tickers[0]]
        else:
            # fallback
            close = df.iloc[:, [0]].copy()
            close.columns = [tickers[0]]

    close.index = pd.to_datetime(close.index)
    close = close.sort_index()

    # Standardize ticker casing
    close.columns = [str(c).upper() for c in close.columns]

    # Ensure all tickers present; if not, fail fast (universe is fixed by contract)
    missing = [t.upper() for t in tickers if t.upper() not in close.columns]
    if missing:
        raise RuntimeError(
            f"yfinance download missing tickers: {missing}. "
            "This may be caused by tz-cache sqlite lock or temporary data source issue. "
            "Try rerun after replacing data_prep.py (threads=False), or switch to csv_folder."
        )

    return close


def _load_csv_folder_adj_close(csv_folder: str, tickers: List[str]) -> pd.DataFrame:
    """
    Expects files: <TICKER>.csv with columns: date, adj_close
    """
    folder = Path(csv_folder)
    frames = []
    for t in tickers:
        fp = folder / f"{t}.csv"
        if not fp.exists():
            raise FileNotFoundError(f"Missing CSV for ticker={t}: {fp}")
        df = pd.read_csv(fp)
        if "date" not in df.columns or "adj_close" not in df.columns:
            raise ValueError(f"{fp} must contain columns: date, adj_close")
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df = df.set_index("date")[["adj_close"]].rename(columns={"adj_close": t.upper()})
        frames.append(df)
    close = pd.concat(frames, axis=1).sort_index()
    return close


def _align_intersection_calendar(close: pd.DataFrame) -> pd.DataFrame:
    """
    Intersection calendar: keep only dates where all tickers have prices.
    """
    aligned = close.dropna(axis=0, how="any")
    return aligned


def _compute_simple_returns(aligned_close: pd.DataFrame) -> pd.DataFrame:
    rets = aligned_close.pct_change().dropna()
    return rets


def prepare_returns(cfg: Dict[str, Any]) -> Dict[str, str]:
    """
    Creates required processed artifacts per data_contract.md:
    - data/processed/returns.parquet (date,ticker,ret)
    - data/processed/assets.json
    - data/processed/aligned_calendar.csv
    """
    tickers = [t.upper() for t in cfg["data"]["tickers"]]
    start = cfg["data"]["start"]
    end = cfg["data"]["end"]
    source = cfg["data"]["source"]
    csv_folder = cfg["data"].get("csv_folder", "data/raw")

    processed_dir = Path("data/processed")
    ensure_dir(processed_dir)

    # project-local yfinance cache directory
    yf_cache_dir = processed_dir / "yfinance_cache"
    ensure_dir(yf_cache_dir)

    if source == "yfinance":
        close = _download_yfinance_adj_close(tickers, start, end, cache_dir=yf_cache_dir)
    elif source == "csv_folder":
        close = _load_csv_folder_adj_close(csv_folder, tickers)
    else:
        raise ValueError("data.source must be one of: yfinance, csv_folder")

    aligned = _align_intersection_calendar(close)
    if aligned.empty:
        raise RuntimeError("Aligned price dataframe is empty after intersection calendar. Check data availability.")
    rets = _compute_simple_returns(aligned)
    if rets.empty:
        raise RuntimeError("Return dataframe is empty after pct_change(). Check date range and data.")

    # Save aligned calendar (prices index)
    aligned_calendar = pd.DataFrame({"date": aligned.index.astype("datetime64[ns]")})
    aligned_calendar_csv = processed_dir / "aligned_calendar.csv"
    aligned_calendar.to_csv(aligned_calendar_csv, index=False)

    # Save returns parquet (long) in robust way (no 'index' assumption)
    rets = rets.copy()
    rets.index.name = "date"
    rets.columns.name = "ticker"
    ret_long = rets.stack().reset_index(name="ret")  # columns: date, ticker, ret

    returns_parquet = processed_dir / "returns.parquet"
    ret_long.to_parquet(returns_parquet, index=False)

    # Save assets metadata (from raw close, not aligned)
    meta = {}
    for t in tickers:
        s = close[t]
        meta[t] = {
            "start": str(pd.to_datetime(s.first_valid_index()).date()) if s.first_valid_index() is not None else None,
            "end": str(pd.to_datetime(s.last_valid_index()).date()) if s.last_valid_index() is not None else None,
            "missing_rate": float(s.isna().mean()),
            "count": int(s.notna().sum()),
        }
    assets_json = processed_dir / "assets.json"
    save_json(assets_json, meta)

    return {
        "returns_parquet": str(returns_parquet),
        "assets_json": str(assets_json),
        "aligned_calendar_csv": str(aligned_calendar_csv),
    }
