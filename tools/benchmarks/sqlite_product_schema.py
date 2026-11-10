"""只在新临时根测试产品SQLite结构；合成证券/日历，不联网、不读取真实配置。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import platform
import pickle
import sqlite3
import statistics
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'python/src'))
from pmi.market_data.storage import Database
from pmi.market_data.storage.database import canonical, digest
from pmi.market_data.storage.database import WRITE_CACHE_KIB, READ_CACHE_KIB
from pmi.market_data.storage.documents import Documents
from pmi.market_data.storage.facts import Facts
from pmi.market_data.storage.originals import Originals
from pmi.market_data.storage.observations import observation
from pmi.market_data.storage.publications import Publications, ValidationProof

POINT = '2026-11-08T00:00:00+08:00'
DOMAIN = 'synthetic-benchmark'
LAYOUT = canonical({'open': 0, 'high': 1, 'low': 2, 'close': 3, 'volume': 4, 'amount': 5}).decode()
SELECT = '''SELECT r.instrument_id,r.trade_date,r.row_version,r.opening,r.high,r.low,r.closing,r.volume,r.amount,
 r.unit,r.precision,r.price_type FROM current_row h
 CROSS JOIN price_projection p INDEXED BY price_projection_lookup
 ON p.instrument_id=h.instrument_id AND p.trade_date=h.trade_date AND p.id=h.projection_id
 CROSS JOIN price_row r INDEXED BY sqlite_autoindex_price_row_2
 ON r.instrument_id=p.instrument_id AND r.trade_date=p.trade_date AND r.id=p.row_id '''
DATE_SELECT = (SELECT.replace('current_row h', 'current_row h INDEXED BY current_row_by_date')
              .replace('price_projection_lookup', 'price_projection_by_date')
              .replace('sqlite_autoindex_price_row_2', 'price_by_date'))

def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)

def days(count):
    result, current = [], date(2016, 1, 4)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result

def fixed(number, scale):
    base = 10 ** scale
    return f'{number // base}.{number % base:0{scale}d}'

def values(symbol, ordinal, revision=0):
    price = 10000 + (symbol * 7919 + ordinal * 104729) % 2000000
    return (fixed(price, 4), fixed(price + 500, 4), fixed(price - 500, 4),
        fixed(price + ordinal % 401 - 200 + revision, 4), str(100000 + symbol * 17 + ordinal),
        fixed(100000000 + symbol * 65537 + ordinal * 104729, 2))

def row(symbol, ordinal, day, revision=0):
    return dict(zip(('trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount'),
                    (day, *values(symbol, ordinal, revision))))

def packed(symbol, ordinal, day, metadata, metadata_hash, node_id, revision=0):
    instrument = f'synthetic:{symbol:06d}'
    value = row(symbol, ordinal, day, revision)
    data = values(symbol, ordinal, revision)
    version = digest([data, '元', 4, 'unadjusted'])
    fact = digest(['price', instrument, day, version])
    projection = digest(['price-projection', instrument, value, '元', 4, 'unadjusted'])
    node_hash = digest(['price', projection, ((None, metadata_hash),)])
    return (
        (fact, instrument, day, version, *data, '元', 4, 'unadjusted'),
        (node_id, node_hash, 'price', projection),
        (node_id, 0, None, metadata),
        (projection, 'price-row', node_id, digest(value)),
        (projection, instrument, day, fact, metadata, LAYOUT),
    )

def verify_codec(connection, dates):
    """优化批量装配的每一列与正式Facts.price实际产物对照；不替代来源准入。"""
    connection.execute('SAVEPOINT codec')
    try:
        facts, docs = Facts(connection), Documents(connection)
        facts.instrument('synthetic:000000', 'stock')
        for ordinal, day in enumerate(dates[:25]):
            value = row(0, ordinal, day)
            projection = facts.price('synthetic:000000', value, unit='元', precision=4, price_type='unadjusted')
            actual = connection.execute('SELECT * FROM price_projection WHERE id=?', (projection,)).fetchone()
            node = connection.execute('SELECT root FROM document WHERE id=?', (projection,)).fetchone()[0]
            mh = connection.execute('SELECT fingerprint FROM node WHERE id=?', (actual[4],)).fetchone()[0]
            expected = packed(0, ordinal, day, actual[4], mh, node)
            for query, identifier, wanted in [
                ('SELECT * FROM price_row WHERE id=?', actual[3], expected[0]),
                ('SELECT * FROM node WHERE id=?', node, expected[1]),
                ('SELECT * FROM node_edge WHERE parent=?', node, expected[2]),
                ('SELECT * FROM document WHERE id=?', projection, expected[3]),
                ('SELECT * FROM price_projection WHERE id=?', projection, expected[4]),
            ]:
                assert tuple(connection.execute(query, (identifier,)).fetchone()) == wanted
            assert docs.get(projection) == value
    finally:
        connection.execute('ROLLBACK TO codec')
        connection.execute('RELEASE codec')

def publication(connection, instrument, count, revision, base=None):
    doc = {'synthetic': True, 'instrument': instrument, 'rows': count, 'revision': revision}
    reference = Documents(connection).put(doc)
    pubs = Publications(connection)
    receipt = pubs.receipt(ValidationProof('synthetic-recipe-v1', digest(doc), POINT, {'synthetic_only': True}))
    connection.execute('INSERT INTO publication VALUES(?,?,?,?,?,?,?,?,?)',
        (reference, DOMAIN, instrument, revision, base, None, None, 'published', receipt))
    return reference

def source_observation(connection, original, publisher, locator):
    return observation(connection, DOMAIN, original, {'source': publisher, 'object_id': original,
        'retrieved_at': POINT, 'published_at': POINT, 'started_at': POINT, 'locator': locator})

def insert_group(connection, symbol, ordinals, dates, meta, *, revision=0, source=None):
    instrument = f'synthetic:{symbol:06d}'
    docs = Documents(connection)
    old = connection.execute('SELECT publication_id FROM current_publication WHERE domain_id=? AND subject=?', (DOMAIN, instrument)).fetchone()
    base = old[0] if old else None
    pub = publication(connection, instrument, len(ordinals), revision, base)
    next_node = connection.execute('SELECT coalesce(max(id),0)+1 FROM node').fetchone()[0]
    groups = [[], [], [], [], [], [], [], []]
    selected = []
    for offset, ordinal in enumerate(ordinals):
        day = dates[ordinal]
        rows = packed(symbol, ordinal, day, *meta[day], next_node + offset, revision)
        for target, data in zip(groups, rows):
            target.append(data)
        fact, projection = rows[0][0], rows[4][0]
        groups[5].append(('price', fact, source, f'row:{ordinal+1}'))
        groups[6].append((pub, 'price', instrument, day, '', projection))
        groups[7].append((DOMAIN, instrument, '', 'price', instrument, day, '', projection))
        selected.append(projection)
    for table, count, data in zip(('price_row', 'node', 'node_edge', 'document', 'price_projection', 'row_provenance', 'publication_row'),
                                  (13, 4, 4, 4, 6, 4, 6), groups):
        connection.executemany(f'INSERT INTO {table} VALUES({",".join("?"*count)})', data)
    connection.executemany('''INSERT INTO current_row VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(domain_id,subject,binding,row_kind,instrument_id,trade_date,metric)
        DO UPDATE SET projection_id=excluded.projection_id''', groups[7])
    connection.execute('''INSERT INTO current_publication VALUES(?,?,?, ?,NULL,NULL)
        ON CONFLICT(domain_id,subject,binding) DO UPDATE SET publication_id=excluded.publication_id''',
        (DOMAIN, instrument, '', pub))
    return pub, selected

def trials(database, sql, params, count, repeat=5):
    samples=[]
    for _ in range(repeat):
        start=time.perf_counter()
        with database.read() as connection:
            result=connection.execute(sql,params).fetchall()
        samples.append(time.perf_counter()-start)
        assert len(result)==count
        assert not result or isinstance(result[0][3],str)
    with database.read() as connection:
        plan=[list(r) for r in connection.execute('EXPLAIN QUERY PLAN '+sql,params)]
    return {'rows':count,'samples_seconds':samples,'max_seconds':max(samples),'median_seconds':statistics.median(samples),'query_plan':plan}

@contextmanager
def staged_batches(path, sort_projection=False):
    def batches(stream):
        while True:
            try: yield pickle.load(stream)
            except EOFError: return
    if not sort_projection:
        with path.open('rb') as stream:
            yield batches(stream)
        return
    # 只排序本进程刚生成的合成暂存；不用关闭事实库约束换取写入速度。
    sorter = sqlite3.connect(path.with_name('projection-sort.sqlite'))
    cursor = None
    temporary = path.parent / 'sort-temporary'; temporary.mkdir(mode=0o700)
    previous = sorter.execute('PRAGMA temp_store_directory').fetchone()
    try:
        sorter.execute('PRAGMA synchronous=FULL')
        sorter.execute('PRAGMA cache_size=-16384')
        sorter.execute('PRAGMA temp_store=FILE')
        sorter.execute("PRAGMA temp_store_directory='" + str(temporary).replace("'", "''") + "'")
        assert sorter.execute('PRAGMA temp_store_directory').fetchone()[0] == str(temporary)
        sorter.execute('CREATE TABLE staging(id TEXT,instrument TEXT,day TEXT,fact TEXT,metadata INTEGER,layout TEXT)')
        with sorter, path.open('rb') as stream:
            for batch in batches(stream):
                sorter.executemany('INSERT INTO staging VALUES(?,?,?,?,?,?)', batch)
        cursor = sorter.execute('SELECT * FROM staging ORDER BY id')
        yield iter(lambda: cursor.fetchmany(2500), [])
    finally:
        if cursor is not None: cursor.close()
        original = previous[0] if previous else ''
        try:
            sorter.execute("PRAGMA temp_store_directory='" + original.replace("'", "''") + "'")
        finally:
            sorter.close()
    assert not any(temporary.iterdir())


def tablewise_load(database, connection, output, symbols, day_count, dates, meta, sources, batch_symbols, started, sort_projection=False):
    """同一最终结构/约束，首装按表顺序写；暂存生成及fsync全部计入首装时间。"""
    publications = {}
    for chunk in range(0, symbols, batch_symbols):
        with database.transaction():
            for symbol in range(chunk, min(chunk + batch_symbols, symbols)):
                raw = b''.join(canonical(row(symbol, n, dates[n])) + b'\n' for n in range(day_count))
                original = Originals(database).put(raw, media_type='application/x-ndjson')
                sources[symbol] = source_observation(connection, original, 'synthetic-recipe-v1', f'synthetic:{symbol}')
                publications[symbol] = publication(connection, f'synthetic:{symbol:06d}', day_count, 0)
    specs = (('price_row', 13), ('node', 4), ('node_edge', 4), ('document', 4), ('price_projection', 6),
             ('row_provenance', 4), ('publication_row', 6), ('current_row', 8))
    spool = output / 'synthetic-staging'; spool.mkdir(mode=0o700)
    streams = [(spool / table).open('xb') for table, _ in specs]
    next_node = connection.execute('SELECT coalesce(max(id),0)+1 FROM node').fetchone()[0]
    try:
        for symbol in range(symbols):
            instrument, groups = f'synthetic:{symbol:06d}', [[] for _ in specs]
            for ordinal in range(day_count):
                on = dates[ordinal]
                rows = packed(symbol, ordinal, on, *meta[on], next_node)
                next_node += 1
                for target, value in zip(groups, rows): target.append(value)
                projection = rows[4][0]
                groups[5].append(('price', rows[0][0], sources[symbol], f'row:{ordinal+1}'))
                groups[6].append((publications[symbol], 'price', instrument, on, '', projection))
                groups[7].append((DOMAIN, instrument, '', 'price', instrument, on, '', projection))
            for stream, data in zip(streams, groups): pickle.dump(data, stream, protocol=5)
            if (symbol+1) % 250 == 0: emit({'stage':'stage-rows','symbols':symbol+1,'seconds':time.perf_counter()-started})
        for stream in streams: stream.flush(); os.fsync(stream.fileno())
    finally:
        for stream in streams: stream.close()
    for table, columns in specs:
        count = 0
        with staged_batches(spool / table, sort_projection and table == 'price_projection') as batches, database.transaction():
            for batch in batches:
                connection.executemany(f'INSERT INTO {table} VALUES({",".join("?"*columns)})', batch)
                count += len(batch)
                if count % 1000000 == 0: emit({'stage':'table-load','table':table,'rows':count,'seconds':time.perf_counter()-started})
        emit({'stage':'table-committed','table':table,'rows':count,'seconds':time.perf_counter()-started})
    with database.transaction():
        connection.executemany('INSERT INTO current_publication VALUES(?,?,?, ?,NULL,NULL)',
            [(DOMAIN, f'synthetic:{symbol:06d}', '', pub) for symbol, pub in publications.items()])
    return publications[0]


def main(output, symbols, day_count, batch_symbols, initial_cache_mib, bulk_mode='interleaved', bulk_only=False, validation_cache_mib=2048):
    if output.exists() or not str(output).startswith('/private/tmp/') or output.resolve()!=output:
        raise ValueError('必须指定尚不存在的独占临时根')
    output.mkdir(mode=0o700)
    (output/'source.py').write_bytes(Path(__file__).read_bytes())
    root=output/'store';root.mkdir(mode=0o700)
    database=Database(root);database.initialize()
    dates=days(day_count+1)
    result={'synthetic_only':True,'symbols':symbols,'stocks':min(6000,symbols),'etfs':max(0,symbols-6000),
        'days':day_count,'rows':symbols*day_count,'sqlite':sqlite3.sqlite_version,'python':sys.version,
        'platform':platform.platform(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'schema_sha256':hashlib.sha256((REPO/'python/src/pmi/market_data/storage/schema.py').read_bytes()).hexdigest(),
        'physical_cold_cache':False,'financial_sources_admitted':False,
        'write_cache_kib':WRITE_CACHE_KIB,'read_cache_kib':READ_CACHE_KIB,
        'initial_transaction_symbols':batch_symbols,'initial_cache_mib':initial_cache_mib,'bulk_mode':bulk_mode,
        'synchronous':'FULL','journal_mode':'DELETE','validation_cache_kib':validation_cache_mib*1024}
    def save():
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    save()
    start=time.perf_counter()
    first_publication=None
    sources={}
    with database.writer() as connection:
        connection.execute(f'PRAGMA cache_size=-{initial_cache_mib*1024}')
        schema_before = [tuple(x) for x in connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        deferred = []
        if bulk_mode == 'tablewise-sorted':
            deferred = [tuple(x) for x in connection.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name")]
            with database.transaction():
                for name, table, ddl in deferred:
                    actual = next(x for x in connection.execute('PRAGMA index_list("'+table+'")') if x[1] == name)
                    assert actual[2] == 0 and actual[3] == 'c' and ddl.startswith('CREATE INDEX ')
                    connection.execute('DROP INDEX "'+name+'"')
            result['deferred_nonunique_indexes'] = [x[0] for x in deferred]
            assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        with database.transaction():
            Publications(connection).domain(DOMAIN, 'synthetic-benchmark-only')
            verify_codec(connection,dates)
            docs=Documents(connection)
            meta={}
            for day in dates:
                node=docs.encode({'trade_date':day})
                meta[day]=(node,connection.execute('SELECT fingerprint FROM node WHERE id=?',(node,)).fetchone()[0])
            connection.executemany('INSERT INTO instrument VALUES(?,?,?,?,?)',
                [(f'synthetic:{s:06d}','stock' if s<6000 else 'etf','synthetic',str(s),'Synthetic') for s in range(symbols)])
        if bulk_mode in ('tablewise', 'tablewise-sorted'):
            first_publication = tablewise_load(database, connection, output, symbols, day_count, dates, meta, sources, batch_symbols, start, bulk_mode == 'tablewise-sorted')
        for chunk in range(0, symbols if bulk_mode == 'interleaved' else 0, batch_symbols):
            with database.transaction():
                for symbol in range(chunk, min(chunk + batch_symbols, symbols)):
                    # 原件保留全部合成OHLC/量额；不只保留一个空文件计去重或备份。
                    raw=b''.join(canonical(row(symbol,n,dates[n]))+b'\n' for n in range(day_count))
                    original=Originals(database).put(raw,media_type='application/x-ndjson')
                    source=source_observation(connection,original,'synthetic-recipe-v1',f'synthetic:{symbol}')
                    sources[symbol]=source
                    pub,_=insert_group(connection,symbol,range(day_count),dates,meta,source=source)
                    if symbol==0:first_publication=pub
            if (symbol+1)%250==0 or chunk==0:emit({'stage':'load','symbols':symbol+1,'seconds':time.perf_counter()-start})
        for name, table, ddl in deferred:
            with database.transaction(): connection.execute(ddl)
            emit({'stage':'index-built','index':name,'seconds':time.perf_counter()-start})
        assert schema_before == [tuple(x) for x in connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        result['final_schema_exact'] = True
    result['bulk_seconds']=time.perf_counter()-start
    result['database_bytes']=database.path.stat().st_size
    result['original_bytes']=sum(p.stat().st_size for p in (root/'objects').iterdir())
    save();emit({'stage':'loaded','seconds':result['bulk_seconds'],'database_bytes':result['database_bytes']})
    if bulk_only:
        with database.read() as connection:
            connection.execute(f'PRAGMA cache_size=-{validation_cache_mib*1024}')
            assert connection.execute('SELECT count(*) FROM price_row').fetchone()[0] == symbols*day_count
            assert connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            assert connection.execute('PRAGMA foreign_key_check').fetchone() is None
        result['bulk_integrity_passed'] = True; save(); return
    one=f'synthetic:{symbols//2:06d}'
    base="WHERE h.domain_id=? AND h.subject=? AND h.binding='' AND h.row_kind='price' "
    result['single']=trials(database,SELECT+base+'ORDER BY h.trade_date',(DOMAIN,one),day_count)
    result['cross_section']=trials(database,DATE_SELECT+"WHERE h.trade_date=? AND h.row_kind='price' ORDER BY h.instrument_id",(dates[day_count-1],),symbols)
    width=min(250,day_count)
    result['single_range']=trials(database,SELECT+base+'AND h.trade_date BETWEEN ? AND ? ORDER BY h.trade_date',(DOMAIN,one,dates[day_count-width],dates[day_count-1]),width)
    width=min(20,day_count)
    result['market_range']=trials(database,DATE_SELECT+"WHERE h.trade_date BETWEEN ? AND ? AND h.row_kind='price' ORDER BY h.trade_date,h.instrument_id",(dates[day_count-width],dates[day_count-1]),width*symbols,3)
    save();emit({'stage':'reads','single':result['single']['max_seconds'],'cross':result['cross_section']['max_seconds']})
    # 日增量：每只一行，新增来源与版本、差量与当前索引均计入。
    start=time.perf_counter()
    with database.writer() as connection,database.transaction():
        for symbol in range(symbols):
            raw=canonical(row(symbol,day_count,dates[-1],1))
            original=Originals(database).put(raw)
            source=source_observation(connection,original,'synthetic-recipe-v1','increment')
            insert_group(connection,symbol,[day_count],dates,meta,revision=1,source=source)
    result['increment_seconds']=time.perf_counter()-start
    save();emit({'stage':'increment','seconds':result['increment_seconds']})
    result['corrections']=[]
    for iteration,changed in enumerate((1,min(100,symbols*day_count),min(1000,symbols*day_count),min(7500,symbols*day_count)),2):
        before=database.path.stat().st_size
        start=time.perf_counter()
        with database.writer() as connection,database.transaction():
            count=connection.execute('SELECT count(*) FROM price_row').fetchone()[0]
            grouped={}
            for n in range(changed):grouped.setdefault(n%symbols,[]).append(n//symbols)
            for symbol,ordinals in grouped.items():
                raw=b''.join(canonical(row(symbol,n,dates[n],iteration))+b'\n' for n in ordinals)
                original=Originals(database).put(raw)
                source=source_observation(connection,original,'synthetic-correction','correction')
                insert_group(connection,symbol,ordinals,dates,meta,revision=iteration,source=source)
            assert connection.execute('SELECT count(*) FROM price_row').fetchone()[0]-count==changed
        elapsed=time.perf_counter()-start
        with database.read() as connection:
            old=Publications(connection).rows(first_publication)
            assert len(old)==day_count
            # 同一内容经正式API重试不增加事实或投影；旧版仍精确可读。
            projection=next(iter(old.values()))
            assert Documents(connection).get(projection)==row(0,0,dates[0])
        with database.writer() as connection,database.transaction():
            before_count=connection.execute('SELECT count(*) FROM price_row').fetchone()[0]
            Facts(connection).price('synthetic:000000',row(0,0,dates[0],iteration),unit='元',precision=4,price_type='unadjusted')
            assert connection.execute('SELECT count(*) FROM price_row').fetchone()[0]==before_count
        item={'changed_rows':changed,'new_facts':changed,'seconds':elapsed,'database_growth_bytes':database.path.stat().st_size-before,'old_version_exact':True,'retry_new_facts':0}
        result['corrections'].append(item);save();emit({'stage':'correction',**item})
    target=output/'backup.sqlite'
    start=time.perf_counter()
    original_target=output/'backup-objects';original_target.mkdir(mode=0o700)
    with database.exclusive_read() as connection:
        destination=sqlite3.connect(target)
        try:connection.backup(destination,pages=1024)
        finally:destination.close()
        result['database_backup_seconds']=time.perf_counter()-start
        original_manifest={}
        for identity,size in connection.execute('SELECT id,byte_length FROM original_object ORDER BY id'):
            raw=Originals(database).get(identity)
            with (original_target/identity).open('xb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            original_manifest[identity]=size
        from pmi.market_data.storage.database import fsync_directory
        fsync_directory(original_target);fsync_directory(output)
    result['database_and_originals_backup_seconds']=time.perf_counter()-start
    save();emit({'stage':'backup','seconds':result['database_backup_seconds']})
    start=time.perf_counter()
    # SQLite backup之后全部表逐列、按原表顺序计算有序指纹；主键/原页复制保证同一顺序。
    def fingerprints(c, side):
        data={}
        for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            checksum=hashlib.sha256();count=0
            for item in c.execute('SELECT * FROM '+table):
                checksum.update(canonical(list(item))+b'\n');count+=1
            data[table]={'rows':count,'sha256':checksum.hexdigest()}
            emit({'stage':'backup-fingerprint','side':side,'table':table,'rows':count})
        return data
    with database.read() as connection:
        left=fingerprints(connection, 'source')
    with sqlite3.connect(target.as_uri()+'?mode=ro',uri=True) as connection:
        connection.execute(f'PRAGMA cache_size=-{validation_cache_mib*1024}')
        right=fingerprints(connection, 'backup')
        emit({'stage':'backup-quick-check'})
        assert connection.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        emit({'stage':'backup-foreign-key-check'})
        assert connection.execute('PRAGMA foreign_key_check').fetchone() is None
    assert left==right
    for identity,size in original_manifest.items():
        raw=(original_target/identity).read_bytes()
        assert len(raw)==size and hashlib.sha256(raw).hexdigest()==identity
    result.update(all_table_fingerprints=left,backup_validation_seconds=time.perf_counter()-start,passed=True)
    save();emit({'stage':'complete','passed':True})

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--symbols',type=int,default=7500)
    parser.add_argument('--days',type=int,default=2500)
    parser.add_argument('--batch-symbols',type=int,default=25)
    parser.add_argument('--initial-cache-mib',type=int,default=1024)
    parser.add_argument('--bulk-mode',choices=('interleaved','tablewise','tablewise-sorted'),default='interleaved')
    parser.add_argument('--bulk-only',action='store_true')
    parser.add_argument('--validation-cache-mib',type=int,default=2048)
    args=parser.parse_args()
    if not 1<=args.symbols<=7500 or not 1<=args.days<=2500 or not 1<=args.batch_symbols<=250 or not 16<=args.initial_cache_mib<=2048:raise ValueError('size')
    if not 16<=args.validation_cache_mib<=6144:raise ValueError('validation cache')
    main(args.output,args.symbols,args.days,args.batch_symbols,args.initial_cache_mib,args.bulk_mode,args.bulk_only,args.validation_cache_mib)
