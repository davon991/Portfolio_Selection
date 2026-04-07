import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import yaml


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_run_id(cfg: Dict[str, Any]) -> str:
    """
    Deterministic run_id based on config content + timestamp (minute-level).
    """
    cfg_bytes = json.dumps(cfg, sort_keys=True).encode("utf-8")
    cfg_hash = sha256_bytes(cfg_bytes)[:10]
    name = cfg["run"]["name"]
    from datetime import datetime
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M")
    return f"{name}-{ts}-{cfg_hash}"


def read_version_from_frozen_doc(path: Path) -> str:
    """
    Reads 'Version:' line from frozen markdown files.
    If missing, returns 'unknown'.
    """
    if not path.exists():
        return "missing"
    for line in path.read_text(encoding="utf-8").splitlines()[:50]:
        if "Version:" in line:
            return line.split("Version:", 1)[1].strip()
    return "unknown"
