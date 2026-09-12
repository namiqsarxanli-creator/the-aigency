"""SQLite bazasını server işləyərkən təhlükəsiz backup edir və dərhal integrity-check aparır."""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def backup(source: Path, destination_dir: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = destination_dir / f"agency-{stamp}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            target.unlink(missing_ok=True)
            raise RuntimeError(f"Backup integrity_check uğursuzdur: {result}")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="agency.db")
    parser.add_argument("--destination", default="backups")
    args = parser.parse_args()
    print(backup(Path(args.source).resolve(), Path(args.destination).resolve()))
