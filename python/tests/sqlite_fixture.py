"""仅供隔离测试显式建库；生产构造/GET绝不调用，不接受非临时目录。"""
from pathlib import Path
from pmi.market_data.storage import Database
from pmi.market_data.storage.database import digest
from pmi.market_data.storage.integrity import Integrity
from pmi.market_data.storage.publications import Publications
from pmi.market_data.storage.validation import check_all

def initialize(root: Path, *, activity: bool = True):
    if not str(root.resolve()).startswith(('/private/tmp/', '/private/var/folders/')):
        raise ValueError('测试建库只允许独占临时目录')
    database = Database(root)
    database.initialize()
    with database.writer(), database.transaction() as connection:
        Publications(connection).domain('price-v2', digest(['synthetic-price', str(root)]))
        if activity:
            Publications(connection).domain('activity', digest(['synthetic-activity', str(root)]))
    Integrity(database).run('full', semantic_check=lambda connection: check_all(database, connection))
    return database

def price_writer(root: Path):
    """替代旧按文件根锁的夹具入口，仍取得真实单库写锁。"""
    return Database(root).writer()

def set_activity_budget(root: Path, value: bytes):
    import json
    from pmi.market_data.storage import state
    database = Database(root)
    with database.writer(), database.transaction() as connection:
        state.write(connection, 'activity', 'network-budget', json.loads(value))

def activity_budget_bytes(root: Path):
    from pmi.market_data.storage import state
    from pmi.market_data.storage.database import canonical
    with Database(root).read() as connection:
        return canonical(state.read(connection, 'activity', 'network-budget'))
