"""显式本地完整性维护；不获取金融数据、不重置额度、不修复热journal。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python/src'))
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.etf_flow.model import FlowError
from pmi.market_data.storage.integrity import Integrity
from pmi.market_data.storage.validation import check_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--kind', choices=('structure', 'full'), default='full')
    parser.add_argument('--release-quarantine', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or not args.output.is_absolute() or args.output.resolve() != args.output:
        parser.error('报告必须是尚不存在的绝对路径')
    if args.release_quarantine and args.kind != 'full':
        parser.error('解除隔离必须进行完整复核')
    database = Database(args.root)
    if args.output == args.root or args.root in args.output.parents:
        parser.error('维护报告必须位于数据库根之外')
    def local_only(event, values):
        if event.startswith('socket.') and event not in ('socket.__new__',) or event in ('subprocess.Popen', 'os.system'):
            raise RuntimeError('完整性维护禁止网络与子进程')
    sys.addaudithook(local_only)
    failure = False
    try:
        result = Integrity(database).run(args.kind, semantic_check=lambda connection: check_all(database, connection),
                                         release_quarantine=args.release_quarantine)
    except (StorageError, FlowError) as error:
        failure = True
        result = {'state': 'failed', 'kind': args.kind, 'code': error.code if isinstance(error, FlowError) else str(error)}
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: result[key] for key in ('state', 'kind', 'id', 'code') if key in result}, ensure_ascii=False))
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
