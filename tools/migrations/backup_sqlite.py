"""单库与原件的一致备份/异地恢复；只操作显式的新格式位置。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python/src'))
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.database import canonical, fsync_directory, location
from pmi.market_data.storage.originals import Originals


def logical_fingerprints(connection: sqlite3.Connection) -> dict:
    """所有业务/维护表逐列有序比对；不能只比较价格或总条数。"""
    result = {}
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for table in tables:
        if not re.fullmatch('[a-z_][a-z_0-9]*', table):
            raise StorageError('backup_unexpected_table')
        columns = [row[1] for row in connection.execute('PRAGMA table_info("' + table + '")')]
        if any(not re.fullmatch('[a-z_][a-z_0-9]*', name) for name in columns):
            raise StorageError('backup_unexpected_column')
        ordering = ','.join('"' + name + '"' for name in columns)
        checksum, count = hashlib.sha256(), 0
        for row in connection.execute('SELECT * FROM "' + table + '" ORDER BY ' + ordering):
            checksum.update(canonical(list(row)) + b'\n')
            count += 1
        result[table] = {'columns': columns, 'rows': count, 'sha256': checksum.hexdigest()}
    return result


def backup(source_root: Path, target_root: Path) -> dict:
    """冻结共用写租约，SQLite在线备份API复制库，逐原件同步后核对。"""
    source = Database(source_root)
    if (target_root.resolve() != target_root or target_root.exists() or source_root == target_root
            or source_root in target_root.parents or target_root in source_root.parents):
        raise StorageError('backup_requires_new_disjoint_target')
    location(target_root.parent, directory=True)
    started = time.perf_counter()
    target_root.mkdir(mode=0o700)
    (target_root / 'objects').mkdir(mode=0o700)
    (target_root / 'incoming').mkdir(mode=0o700)
    lock = os.open(target_root / '.writer.lock', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fsync(lock)
    os.close(lock)
    with source.exclusive_read() as reader:
        before = logical_fingerprints(reader)
        destination = target_root / source.path.name
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        writer = sqlite3.connect(destination)
        try:
            reader.backup(writer, pages=1024)
        finally:
            writer.close()
        raw_manifest = {}
        originals = Originals(source)
        for identity, size in reader.execute('SELECT id,byte_length FROM original_object ORDER BY id'):
            raw = originals._bytes(source_root / 'objects' / identity, 64 * 1024 * 1024)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != identity:
                raise StorageError('backup_original_changed')
            target = target_root / 'objects' / identity
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                pending = memoryview(raw)
                while pending:
                    count = os.write(descriptor, pending)
                    if count <= 0:
                        raise OSError('backup_short_write')
                    pending = pending[count:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            raw_manifest[identity] = size
        fsync_directory(target_root / 'objects')
        fsync_directory(target_root)
        fsync_directory(target_root.parent)
    restored = Database(target_root)
    with restored.read() as connection:
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise StorageError('backup_integrity_failed')
        after = logical_fingerprints(connection)
    if before != after:
        raise StorageError('backup_logical_mismatch')
    for identity in raw_manifest:
        Originals(restored).get(identity)
    return {'passed': True, 'seconds': time.perf_counter() - started, 'tables': before,
        'original_count': len(raw_manifest), 'original_bytes': sum(raw_manifest.values()),
        'original_manifest_sha256': hashlib.sha256(canonical(raw_manifest)).hexdigest(),
        'database_bytes': restored.path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.is_absolute() or args.output.resolve() != args.output:
        raise StorageError('backup_report_exists')
    if any(args.output == root or root in args.output.parents for root in (args.source, args.target)):
        raise StorageError('backup_report_must_be_outside_stores')
    result = backup(args.source, args.target)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != 'tables'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
