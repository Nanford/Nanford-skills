"""
INPUT: 项目 costs/ledger.json；fsutil.py 原子写入
OUTPUT: add_cost_entry() 追加费用记录；summarize_costs() 按「已结算 + 未结算占用」汇总
POS: 费用账本的唯一写入者。未知金额记为 None，不记 0，避免把未对账的费用当作免费。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import SCHEMA_VERSION
from .fsutil import now_iso, read_json, write_json_atomic

LEDGER_FILE = Path("costs") / "ledger.json"
SETTLEMENT_STATUSES = ("estimated", "reserved", "settled", "unknown")


@dataclass
class CostEntry:
    service: str
    unit: str
    quantity: float
    request_id: str | None = None
    currency: str = "CNY"
    estimated: float | None = None
    actual: float | None = None
    settlement_status: str = "unknown"
    unit_price_source: str | None = None
    note: str | None = None


def add_cost_entry(project_root: Path, entry: CostEntry) -> dict[str, Any]:
    if entry.settlement_status not in SETTLEMENT_STATUSES:
        raise ValueError(f"结算状态只能是 {SETTLEMENT_STATUSES}")
    if entry.quantity < 0:
        raise ValueError("数量不能为负")
    path = project_root / LEDGER_FILE
    ledger = read_json(path) if path.exists() else {"schema_version": SCHEMA_VERSION, "currency": "CNY", "entries": []}
    if entry.request_id and any(e.get("request_id") == entry.request_id for e in ledger["entries"]):
        raise ValueError(f"请求 {entry.request_id} 已记账，同一请求只记一次")
    record = {"entry_id": f"cost_{len(ledger['entries']) + 1:04d}", "recorded_at": now_iso(), **entry.__dict__}
    ledger["entries"].append(record)
    write_json_atomic(path, ledger)
    return record


def summarize_costs(project_root: Path) -> dict[str, Any]:
    """已结算取 actual；未结算取 estimated 作为占用；两者都未知的条目单独计数，不当作 0。"""
    path = project_root / LEDGER_FILE
    entries = read_json(path)["entries"] if path.exists() else []
    settled = sum(e["actual"] for e in entries if e["settlement_status"] == "settled" and e["actual"] is not None)
    reserved = sum(e["estimated"] for e in entries if e["settlement_status"] != "settled" and e["estimated"] is not None)
    unknown = sum(1 for e in entries if (e["actual"] if e["settlement_status"] == "settled" else e["estimated"]) is None)
    return {"settled": round(settled, 4), "reserved": round(reserved, 4), "unknown_entries": unknown, "entries": len(entries)}
