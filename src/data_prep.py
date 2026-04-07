from __future__ import annotations

import json
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


def _download_yfinance_adj_close(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    df = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )
    # When multiple tickers: columns are MultiIndex (PriceField, Ticker)
    if isinstance(df.columns, pd.MultiIndex):
        if ("Close" in df.columns.get_level_values(0)) and ("Adj Close" not in df.columns.get_level_values(0)):
            close = df["Close"].copy()
        elif "Adj Close" in df.columns.get_level_values(0):
            close = df["Adj Close"].copy()
        else:
            close = df.xs(df.columns.levels[0][0], level=0, axis=1).copy()
    else:
        # single ticker
        close = df["Close"].to_frame(name=tickers[0])
    close.index = pd.to_datetime(close.index)
    close = close.sort_index()
    close.columns = [c.upper() for c in close.columns]
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
        df = df.set_index("date")[["adj_close"]].rename(columns={"adj_close": t})
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

    if source == "yfinance":
        close = _download_yfinance_adj_close(tickers, start, end)
    elif source == "csv_folder":
        close = _load_csv_folder_adj_close(csv_folder, tickers)
    else:
        raise ValueError("data.source must be one of: yfinance, csv_folder")

    aligned = _align_intersection_calendar(close)
    rets = _compute_simple_returns(aligned)

    # Save aligned calendar
    aligned_calendar = pd.DataFrame({"date": aligned.index.astype("datetime64[ns]")})
    aligned_calendar_csv = processed_dir / "aligned_calendar.csv"
    aligned_calendar.to_csv(aligned_calendar_csv, index=False)

    # Save returns parquet (long)
    ret_long = (
        rets.reset_index()
        .melt(id_vars=["index"], var_name="ticker", value_name="ret")
        .rename(columns={"index": "date"})
    )
    returns_parquet = processed_dir / "returns.parquet"
    ret_long.to_parquet(returns_parquet, index=False)

    # Save assets metadata
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
