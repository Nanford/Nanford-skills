"""Durable send reservations prevent automatic retries of uncertain deliveries."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3

import setup_state


def key(policy_id, enterprise):
    value = str(policy_id).strip()
    if value.endswith(".0"):
        value = value[:-2]
    return f"{value}|{str(enterprise).strip()}"


class Ledger:
    def __init__(self, directory):
        self.path = Path(directory) / "notifications.sqlite"

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("CREATE TABLE IF NOT EXISTS deliveries (match_key TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL, reference TEXT NOT NULL)")
        return db

    def blocked(self):
        if not self.path.exists():
            return set()
        db = self.connect()
        try:
            return {row[0] for row in db.execute("SELECT match_key FROM deliveries WHERE status IN ('sending', 'sent')")}
        finally:
            db.close()

    def reserve(self, keys):
        keys = sorted(set(keys))
        if not keys:
            raise ValueError("没有可发送的通知")
        db = self.connect()
        try:
            # One transaction reserves the whole batch before any network request.
            db.execute("BEGIN IMMEDIATE")
            for value in keys:
                existing = db.execute("SELECT status FROM deliveries WHERE match_key=?", (value,)).fetchone()
                if existing and existing[0] in ("sending", "sent"):
                    raise ValueError("通知已发送或结果待核对，禁止自动重发：" + value)
                db.execute("INSERT OR REPLACE INTO deliveries VALUES (?, 'sending', ?, '')",
                           (value, dt.datetime.now(dt.timezone.utc).isoformat()))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def finish(self, keys, reference):
        if not reference:
            raise ValueError("缺少发送回执")
        db = self.connect()
        try:
            with db:
                for value in set(keys):
                    db.execute("INSERT OR REPLACE INTO deliveries VALUES (?, 'sent', ?, ?)",
                               (value, dt.datetime.now(dt.timezone.utc).isoformat(), reference))
        finally:
            db.close()

    def resolve(self, value, status, reference):
        if status not in ("sent", "pending") or not reference:
            raise ValueError("核对结果必须为 sent 或 pending，并提供核对依据")
        db = self.connect()
        try:
            with db:
                previous = db.execute("SELECT status FROM deliveries WHERE match_key=?", (value,)).fetchone()
                if not previous or previous[0] != "sending":
                    raise ValueError("只允许核对发送结果不明的记录；成功记录不得重置")
                db.execute("UPDATE deliveries SET status=?, updated_at=?, reference=? WHERE match_key=?",
                           (status, dt.datetime.now(dt.timezone.utc).isoformat(), reference, value))
        finally:
            db.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="通知发送预留与异常核对")
    sub = ap.add_subparsers(dest="command", required=True)
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--keys", nargs="+", required=True)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--key", required=True)
    resolve.add_argument("--status", choices=["sent", "pending"], required=True)
    resolve.add_argument("--reference", required=True, help="平台查询结果或人工核对记录，不含凭证")
    sub.add_parser("status")
    sub.add_parser("repair-local", help="只补写台账已成功项目的 Excel 通知状态，不发送消息")
    args = ap.parse_args(argv)
    ledger = Ledger(setup_state.data_dir())
    if args.command == "reserve":
        ledger.reserve(args.keys)
    elif args.command == "resolve":
        ledger.resolve(args.key, args.status, args.reference)
    elif args.command == "repair-local":
        if not ledger.path.exists():
            return 0
        db = ledger.connect()
        try:
            sent = [row[0] for row in db.execute("SELECT match_key FROM deliveries WHERE status='sent'")]
        finally:
            db.close()
        from dingtalk_notify import write_notification_status
        keys = {value.replace("|", "||", 1) for value in sent}
        changed = write_notification_status(str(setup_state.data_dir() / "match_results.xlsx"), keys)
        print(f"已补写 {changed} 条通知状态，未发送消息。")
    elif ledger.path.exists():
        db = ledger.connect()
        try:
            print(json.dumps([dict(zip(("key", "status", "updated_at", "reference"), row))
                              for row in db.execute("SELECT * FROM deliveries")], ensure_ascii=False, indent=2))
        finally:
            db.close()
    else:
        print("[]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
