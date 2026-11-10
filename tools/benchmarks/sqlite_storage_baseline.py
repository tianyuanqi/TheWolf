"""仅以标准库生成隔离合成库，测量行版本候选结构；不导入产品模块。"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import sys
import time


SCHEMA = """
CREATE TABLE instrument(id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL CHECK(kind IN ('stock','etf'))) STRICT;
CREATE TABLE publication(version INTEGER PRIMARY KEY, parent INTEGER,
  acquired_at TEXT NOT NULL, reason TEXT NOT NULL) STRICT;
CREATE TABLE evidence(id INTEGER PRIMARY KEY, fingerprint BLOB NOT NULL UNIQUE,
  source TEXT NOT NULL, acquired_at TEXT NOT NULL, relative_path TEXT NOT NULL) STRICT;
CREATE TABLE daily(
  instrument INTEGER NOT NULL REFERENCES instrument(id), day TEXT NOT NULL,
  version INTEGER NOT NULL REFERENCES publication(version),
  open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
  volume TEXT NOT NULL, amount TEXT NOT NULL,
  evidence INTEGER NOT NULL REFERENCES evidence(id), published_at TEXT,
  acquired_at TEXT NOT NULL, content_hash BLOB NOT NULL CHECK(length(content_hash)=32),
  PRIMARY KEY(instrument,day,version)) STRICT, WITHOUT ROWID;
CREATE TABLE current_row(instrument INTEGER NOT NULL, day TEXT NOT NULL, version INTEGER NOT NULL,
  PRIMARY KEY(instrument,day),
  FOREIGN KEY(instrument,day,version) REFERENCES daily(instrument,day,version)) STRICT, WITHOUT ROWID;
CREATE TABLE current_publication(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  version INTEGER NOT NULL REFERENCES publication(version)) STRICT;
"""
SELECT_CURRENT = """SELECT d.* FROM current_row h JOIN daily d
  ON d.instrument=h.instrument AND d.day=h.day AND d.version=h.version """
INSERT_DAILY = "INSERT INTO daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def fixed(value: int, scale: int) -> str:
    base = 10 ** scale
    return f"{value // base}.{value % base:0{scale}d}"


def content_hash(symbol: int, on: str, values: tuple[str, ...]) -> bytes:
    return hashlib.sha256("|".join((str(symbol), on, *values)).encode()).digest()


def dates(count: int) -> list[str]:
    """生成工作日样式的假日历；不代表任何交易所的真实交易日。"""
    result, day = [], date(2016, 1, 4)
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


def synthetic(symbol: int, ordinal: int, on: str, version: int = 1) -> tuple:
    price = 10000 + (symbol * 7919 + ordinal * 104729) % 2000000
    values = (fixed(price, 4), fixed(price + 500, 4), fixed(price - 500, 4),
              fixed(price + ordinal % 401 - 200, 4), str(100000 + symbol * 17 + ordinal),
              fixed(100000000 + symbol * 65537 + ordinal * 104729, 2))
    return (symbol, on, version, *values, symbol, on + "T08:00:00Z",
            "2026-11-07T00:00:00Z", content_hash(symbol, on, values))


def connect(path: Path, *, reader: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + ("?mode=ro" if reader else "?mode=rw"), uri=True)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA cache_size=-65536")
    connection.execute("PRAGMA mmap_size=0")
    if reader:
        connection.execute("PRAGMA query_only=ON")
    else:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA wal_autocheckpoint=1000")
    return connection


def checkpoint(connection: sqlite3.Connection) -> list[int]:
    result = list(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
    if result[0] != 0:
        raise RuntimeError(f"检查点未完成：{result}")
    return result


def sizes(path: Path) -> dict:
    return {suffix or "db": Path(str(path) + suffix).stat().st_size
            if Path(str(path) + suffix).exists() else 0 for suffix in ("", "-wal", "-shm")}


def quantiles(samples: list[float]) -> dict:
    return {"samples_seconds": samples, "median_seconds": statistics.median(samples),
            "p95_seconds": sorted(samples)[math.ceil(.95 * len(samples)) - 1],
            "max_seconds": max(samples)}


def query_trials(path: Path, sql: str, params: tuple, expected: int, *, repeats: int = 10) -> dict:
    """计时包含SQL执行和全部字段取回；不将计数查询充当读取。"""
    def run(connection: sqlite3.Connection) -> tuple[float, list]:
        started = time.perf_counter()
        rows = connection.execute(sql, params).fetchall()
        elapsed = time.perf_counter() - started
        if len(rows) != expected:
            raise AssertionError((expected, len(rows)))
        if rows:
            assert isinstance(rows[0][3], str) and len(rows[0][-1]) == 32
        return elapsed, rows

    started = time.perf_counter()
    with connect(path, reader=True) as first:
        plan = [list(r) for r in first.execute("EXPLAIN QUERY PLAN " + sql, params)]
        first_seconds, rows = run(first)
    first.close()
    open_and_first = time.perf_counter() - started
    del rows
    samples = []
    with connect(path, reader=True) as warm:
        for _ in range(repeats):
            elapsed, rows = run(warm)
            samples.append(elapsed)
            del rows
    warm.close()
    return {"rows": expected, "first_query_seconds": first_seconds,
            "open_plan_and_first_seconds": open_and_first, "query_plan": plan, **quantiles(samples)}


def logical_fingerprint(connection: sqlite3.Connection) -> dict:
    """对全部事实字段、元数据及当前索引计算有序摘要。"""
    result = {}
    for label, sql in {
        "daily": "SELECT * FROM daily ORDER BY instrument,day,version",
        "current_row": "SELECT instrument,day,version FROM current_row ORDER BY instrument,day",
        "evidence": "SELECT * FROM evidence ORDER BY id",
        "publication": "SELECT * FROM publication ORDER BY version",
        "instrument": "SELECT * FROM instrument ORDER BY id",
        "current_publication": "SELECT * FROM current_publication ORDER BY singleton",
    }.items():
        digest, count = hashlib.sha256(), 0
        for row in connection.execute(sql):
            digest.update((repr(row) + "\n").encode())
            count += 1
        result[label] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def add_evidence(connection: sqlite3.Connection, root: Path, identifier: int, label: str) -> None:
    raw = json.dumps({"synthetic": True, "generator": "sqlite-storage-baseline-v1", "label": label},
                     sort_keys=True).encode()
    fingerprint = hashlib.sha256(raw).digest()
    name = fingerprint.hex()
    path = root / "objects" / name
    path.write_bytes(raw)
    connection.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", (
        identifier, fingerprint, "synthetic-only", "2026-11-07T00:00:00Z", "objects/" + name))


def run(root: Path, stocks: int, etfs: int, days: int) -> dict:
    """运行候选表结构；所有写入均限定在新建临时目录内。"""
    n = stocks + etfs
    total = n * days
    calendar = dates(days + 1)
    path = root / "market.sqlite"
    (root / "objects").mkdir()
    result = {"synthetic_only": True, "stocks": stocks, "etfs": etfs, "days": days,
              "expected_initial_rows": total, "python": sys.version, "sqlite": sqlite3.sqlite_version,
              "platform": platform.platform(), "cache_kib": 65536, "mmap_bytes": 0,
              "cold_cache": "未清理操作系统文件缓存；新连接不等于物理冷盘",
              "schema_sha256": hashlib.sha256(SCHEMA.encode()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "root": str(root), "pid": os.getpid(), "free_disk_before": shutil.disk_usage(root).free}
    started = time.perf_counter()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA page_size=4096")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA cache_size=-65536")
    connection.execute("PRAGMA mmap_size=0")
    connection.executescript(SCHEMA)
    result["pragmas"] = {key: connection.execute("PRAGMA " + key).fetchone()[0]
                         for key in ("page_size", "journal_mode", "synchronous", "foreign_keys", "cache_size", "mmap_size")}
    with connection:
        connection.execute("INSERT INTO publication VALUES(1,NULL,?,?)", ("2026-11-07T00:00:00Z", "synthetic initial"))
        connection.executemany("INSERT INTO instrument VALUES(?,?,?)", (
            (i, f"SYN{i:06d}", "stock" if i <= stocks else "etf") for i in range(1, n + 1)))
        for i in range(1, n + 1):
            add_evidence(connection, root, i, f"instrument:{i}")
    generation_seconds = insertion_seconds = 0.0
    for low in range(1, n + 1, 50):
        high = min(low + 49, n)
        tick = time.perf_counter()
        rows = [synthetic(i, j, calendar[j]) for i in range(low, high + 1) for j in range(days)]
        generation_seconds += time.perf_counter() - tick
        tick = time.perf_counter()
        with connection:
            connection.executemany(INSERT_DAILY, rows)
            connection.execute("INSERT INTO current_row SELECT instrument,day,version FROM daily WHERE instrument BETWEEN ? AND ?", (low, high))
        insertion_seconds += time.perf_counter() - tick
        del rows
        checkpoint(connection)
        if high % 500 == 0 or high == n:
            emit({"stage": "initial_write", "rows": high * days, "elapsed_seconds": time.perf_counter() - started})
    index_start = time.perf_counter()
    with connection:
        connection.execute("CREATE INDEX current_by_day ON current_row(day,instrument)")
        connection.execute("INSERT INTO current_publication VALUES(1,1)")
        connection.execute("ANALYZE")
    checkpoint(connection)
    result["initial_write"] = {"total_seconds": time.perf_counter() - started,
        "generation_hash_seconds": generation_seconds, "insertion_commit_seconds": insertion_seconds,
        "index_analyze_checkpoint_seconds": time.perf_counter() - index_start, "sizes": sizes(path)}
    result["initial_counts"] = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                                 for table in ("daily", "current_row", "instrument", "evidence", "publication")}
    assert result["initial_counts"]["daily"] == result["initial_counts"]["current_row"] == total
    for symbol, ordinal in ((1, 0), (max(1, stocks), days // 2), (n, days - 1)):
        actual = connection.execute("SELECT * FROM daily WHERE instrument=? AND day=? AND version=1", (symbol, calendar[ordinal])).fetchone()
        assert actual == synthetic(symbol, ordinal, calendar[ordinal])
    try:
        result["space_by_object"] = [list(row) for row in connection.execute("SELECT name,count(*),sum(pgsize),sum(payload) FROM dbstat GROUP BY name")]
    except sqlite3.OperationalError as error:
        result["space_by_object_unavailable"] = str(error)
    emit({"stage": "initial_complete", **result["initial_write"]})
    selected = max(1, n // 2)
    result["reads"] = {}
    queries = {
        "single_2500_days": ("WHERE h.instrument=? AND h.day BETWEEN ? AND ? ORDER BY h.day", (selected, calendar[0], calendar[days - 1]), days),
        "market_one_day": ("WHERE h.day=? ORDER BY h.instrument", (calendar[days - 1],), n),
        "single_250_days": ("WHERE h.instrument=? AND h.day BETWEEN ? AND ? ORDER BY h.day", (selected, calendar[max(0, days - 250)], calendar[days - 1]), min(250, days)),
        "market_20_days": ("WHERE h.day BETWEEN ? AND ? ORDER BY h.day,h.instrument", (calendar[max(0, days - 20)], calendar[days - 1]), n * min(20, days)),
    }
    for label, (where, params, expected) in queries.items():
        result["reads"][label] = query_trials(path, SELECT_CURRENT + where, params, expected)
        emit({"stage": "read", "query": label, **result["reads"][label]})
    samples = []
    with connect(path, reader=True) as reader:
        for _ in range(10):
            tick = time.perf_counter()
            reader.execute("BEGIN")
            version = reader.execute("SELECT version FROM current_publication").fetchone()[0]
            rows = reader.execute(SELECT_CURRENT + "WHERE h.day=?", (calendar[days - 1],)).fetchall()
            for symbol in range(1, min(4, n) + 1):
                history = reader.execute(SELECT_CURRENT + "WHERE h.instrument=? AND h.day BETWEEN ? AND ? ORDER BY h.day",
                    (symbol, calendar[max(0, days - 750)], calendar[days - 1])).fetchall()
                assert len(history) == min(750, days)
            reader.rollback()
            samples.append(time.perf_counter() - tick)
            assert version == 1 and len(rows) == n
    reader.close()
    result["homepage_database_proxy"] = quantiles(samples)
    result["homepage_database_proxy"]["not_end_to_end"] = True
    tick = time.perf_counter()
    with connection:
        connection.execute("INSERT INTO publication VALUES(2,1,?,?)", ("2026-11-07T00:01:00Z", "synthetic daily increment"))
        daily_rows = [synthetic(i, days, calendar[days], 2) for i in range(1, n + 1)]
        connection.executemany(INSERT_DAILY, daily_rows)
        connection.executemany("INSERT INTO current_row VALUES(?,?,?)", (r[:3] for r in daily_rows))
        connection.execute("UPDATE current_publication SET version=2")
    before_checkpoint = sizes(path)
    checkpoint(connection)
    result["daily_increment"] = {"rows": n, "seconds_including_checkpoint": time.perf_counter() - tick,
                                  "before_checkpoint": before_checkpoint, "after_checkpoint": sizes(path)}
    emit({"stage": "daily_increment", **result["daily_increment"]})
    result["corrections"] = []
    revision = 2
    for changed in (1, 100, 1000, 7500, 75000):
        if changed > total:
            continue
        revision += 1
        before = sizes(path)
        tick = time.perf_counter()
        keys = [((j * 7919 + revision * 97) % total) for j in range(changed)]
        assert len(set(keys)) == changed
        rows = []
        old_checks = []
        with connection:
            connection.execute("INSERT INTO publication VALUES(?,?,?,?)", (revision, revision - 1, "2026-11-07T00:02:00Z", "synthetic correction"))
            evidence = n + revision
            add_evidence(connection, root, evidence, f"correction:{revision}")
            for key in keys:
                symbol, ordinal = key // days + 1, key % days
                old = connection.execute(SELECT_CURRENT + "WHERE h.instrument=? AND h.day=?", (symbol, calendar[ordinal])).fetchone()
                values = (*old[3:8], str(Decimal(old[8]) + Decimal("0.01")))
                row = (symbol, calendar[ordinal], revision, *values, evidence, old[10],
                       "2026-11-07T00:02:00Z", content_hash(symbol, calendar[ordinal], values))
                rows.append(row)
                if len(old_checks) < 10:
                    old_checks.append(old)
            connection.executemany(INSERT_DAILY, rows)
            connection.executemany("UPDATE current_row SET version=? WHERE instrument=? AND day=?", ((revision, r[0], r[1]) for r in rows))
            connection.execute("UPDATE current_publication SET version=?", (revision,))
        wal = sizes(path)
        checkpoint(connection)
        seconds = time.perf_counter() - tick
        assert connection.execute("SELECT count(*) FROM daily WHERE version=?", (revision,)).fetchone()[0] == changed
        for old in old_checks:
            assert connection.execute("SELECT * FROM daily WHERE instrument=? AND day=? AND version=?", old[:3]).fetchone() == old
            original = connection.execute("SELECT * FROM daily WHERE instrument=? AND day=? AND version=1", old[:2]).fetchone()
            ordinal = calendar.index(old[1])
            assert original == synthetic(old[0], ordinal, old[1])
        before_changes = connection.total_changes
        with connection:
            for row in rows:
                current_hash = connection.execute("SELECT d.content_hash FROM current_row h JOIN daily d USING(instrument,day,version) WHERE h.instrument=? AND h.day=?", row[:2]).fetchone()[0]
                if current_hash != row[-1]:
                    raise AssertionError("同内容重试应在发布前跳过")
        assert connection.total_changes == before_changes
        item = {"version": revision, "changed_rows": changed, "appended_rows": changed,
                "seconds_including_checkpoint": seconds, "db_growth_bytes": sizes(path)["db"] - before["db"],
                "wal_bytes_before_checkpoint": wal["-wal"], "sizes_after_checkpoint": sizes(path),
                "old_versions_verified": True, "idempotent_changes": 0}
        result["corrections"].append(item)
        emit({"stage": "correction", **item})
    result["reads_after_corrections"] = query_trials(path, SELECT_CURRENT + "WHERE h.instrument=? ORDER BY h.day", (selected,), days + 1)
    old_sql = """SELECT d.* FROM daily d WHERE d.instrument=? AND d.day BETWEEN ? AND ? AND d.version=(
      SELECT max(v.version) FROM daily v WHERE v.instrument=d.instrument AND v.day=d.day AND v.version<=?) ORDER BY d.day"""
    result["old_version_read"] = query_trials(path, old_sql, (selected, calendar[0], calendar[days - 1], 1), days)
    tick = time.perf_counter()
    backup_path = root / "backup.sqlite"
    backup = sqlite3.connect(backup_path)
    connection.backup(backup, pages=2048)
    backup.close()
    result["backup"] = {"seconds": time.perf_counter() - tick, "size_bytes": backup_path.stat().st_size,
                        "method": "sqlite3.Connection.backup; same local volume; no concurrent writer"}
    emit({"stage": "backup", **result["backup"]})
    tick = time.perf_counter()
    result["integrity"] = {"source_quick_check": connection.execute("PRAGMA quick_check").fetchall(),
                            "source_foreign_key_check": connection.execute("PRAGMA foreign_key_check").fetchall()}
    source_fingerprint = logical_fingerprint(connection)
    with connect(backup_path, reader=True) as saved:
        result["integrity"]["backup_quick_check"] = saved.execute("PRAGMA quick_check").fetchall()
        backup_fingerprint = logical_fingerprint(saved)
    saved.close()
    assert source_fingerprint == backup_fingerprint
    assert result["integrity"]["source_quick_check"] == result["integrity"]["backup_quick_check"] == [("ok",)]
    assert result["integrity"]["source_foreign_key_check"] == []
    result["integrity"].update({"fingerprints": source_fingerprint, "backup_equal": True,
                               "verification_seconds": time.perf_counter() - tick})
    result["final_counts"] = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                              for table in ("daily", "current_row", "evidence", "publication")}
    assert result["final_counts"]["daily"] == total + n + sum(r["changed_rows"] for r in result["corrections"])
    assert result["final_counts"]["current_row"] == total + n
    checkpoint(connection)
    connection.close()
    result["final_sizes"] = sizes(path)
    result["objects_bytes"] = sum(p.stat().st_size for p in (root / "objects").iterdir())
    result["free_disk_after"] = shutil.disk_usage(root).free
    result["success"] = True
    (root / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    emit({"stage": "complete", "result": str(root / "results.json"), "counts": result["final_counts"]})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="/private/tmp中的全新独占目录")
    parser.add_argument("--stocks", type=int, default=6000)
    parser.add_argument("--etfs", type=int, default=1500)
    parser.add_argument("--days", type=int, default=2500)
    args = parser.parse_args()
    target = args.work_dir.absolute()
    if target.exists() or target.is_symlink() or target.parent.resolve() != target.parent or not target.is_relative_to(Path("/private/tmp")):
        parser.error("必须指定/private/tmp下不存在且无链接父目录的新目录")
    if min(args.stocks, args.etfs, args.days) < 1:
        parser.error("规模必须为正整数")
    if shutil.disk_usage(target.parent).free < 20 * 1024 ** 3:
        parser.error("需要至少20GiB空闲临时磁盘空间")
    target.mkdir(mode=0o700)
    run(target, args.stocks, args.etfs, args.days)
