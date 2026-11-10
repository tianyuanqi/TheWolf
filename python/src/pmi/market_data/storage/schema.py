"""事实值按行，发布/来源与元数据分开；版本行不可变。"""
SCHEMA = '''
CREATE TABLE store_identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_id TEXT NOT NULL UNIQUE, schema_version INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE domain(id TEXT PRIMARY KEY, logical_scope TEXT NOT NULL UNIQUE, initialized INTEGER NOT NULL CHECK(initialized IN(0,1)), legacy_root TEXT);
CREATE TABLE original_object(id TEXT PRIMARY KEY CHECK(length(id)=64), byte_length INTEGER NOT NULL CHECK(byte_length>=0), media_type TEXT NOT NULL);
CREATE TABLE node(id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE CHECK(length(fingerprint)=64), kind TEXT NOT NULL CHECK(kind IN('null','bool','int','str','dict','list','chunk','price','metric','adjustment','source_price','price_snapshot','activity_snapshot')), atom TEXT);
CREATE TABLE node_edge(parent INTEGER NOT NULL REFERENCES node(id), position INTEGER NOT NULL CHECK(position>=0), name TEXT, child INTEGER NOT NULL REFERENCES node(id), PRIMARY KEY(parent,position), UNIQUE(parent,name)) WITHOUT ROWID;
CREATE TABLE document(id TEXT PRIMARY KEY CHECK(length(id)=64), kind TEXT NOT NULL, root INTEGER NOT NULL REFERENCES node(id), canonical_sha256 TEXT NOT NULL CHECK(length(canonical_sha256)=64));
CREATE TABLE document_original(document_id TEXT NOT NULL REFERENCES document(id), original_id TEXT NOT NULL REFERENCES original_object(id), PRIMARY KEY(document_id,original_id)) WITHOUT ROWID;
CREATE TABLE instrument(id TEXT PRIMARY KEY, kind TEXT NOT NULL, exchange TEXT, code TEXT, name TEXT);
CREATE TABLE price_row(id TEXT PRIMARY KEY CHECK(length(id)=64), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, row_version TEXT NOT NULL CHECK(length(row_version)=64), opening TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, closing TEXT NOT NULL, volume TEXT, amount TEXT, unit TEXT NOT NULL, precision INTEGER NOT NULL CHECK(precision>=0), price_type TEXT NOT NULL CHECK(price_type IN('unadjusted','index_points')), UNIQUE(instrument_id,trade_date,row_version));
CREATE INDEX price_by_date ON price_row(trade_date,instrument_id,id,row_version,opening,high,low,closing,volume,amount,unit,precision,price_type);
CREATE TABLE daily_metric(id TEXT PRIMARY KEY CHECK(length(id)=64), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, metric TEXT NOT NULL, row_version TEXT NOT NULL CHECK(length(row_version)=64), value TEXT, unit TEXT NOT NULL, missing_reason TEXT, UNIQUE(instrument_id,trade_date,metric,row_version), CHECK((value IS NOT NULL AND missing_reason IS NULL) OR (value IS NULL AND missing_reason IS NOT NULL)));
CREATE INDEX metric_by_date ON daily_metric(trade_date,metric,instrument_id,row_version);
CREATE TABLE source_price_value(id TEXT PRIMARY KEY CHECK(length(id)=64), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, opening TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, closing TEXT NOT NULL, raw_open TEXT NOT NULL, raw_high TEXT NOT NULL, raw_low TEXT NOT NULL, raw_close TEXT NOT NULL, comparison_open TEXT NOT NULL, comparison_high TEXT NOT NULL, comparison_low TEXT NOT NULL, comparison_close TEXT NOT NULL);
CREATE TABLE source_price_binding(object_id TEXT NOT NULL REFERENCES original_object(id), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, value_id TEXT NOT NULL REFERENCES source_price_value(id), locator TEXT NOT NULL, PRIMARY KEY(object_id,instrument_id,trade_date)) WITHOUT ROWID;
CREATE TABLE source_price_projection(id TEXT PRIMARY KEY REFERENCES document(id), value_id TEXT NOT NULL REFERENCES source_price_value(id), metadata INTEGER NOT NULL REFERENCES node(id), comparison INTEGER NOT NULL CHECK(comparison IN(0,1)));
CREATE TABLE source_observation(id TEXT PRIMARY KEY, domain_id TEXT NOT NULL REFERENCES domain(id), source TEXT NOT NULL, object_id TEXT NOT NULL REFERENCES original_object(id), published_at TEXT, started_at TEXT, retrieved_at TEXT NOT NULL, locator TEXT, metadata TEXT REFERENCES document(id));
CREATE TABLE row_provenance(kind TEXT NOT NULL, row_id TEXT NOT NULL, observation_id TEXT NOT NULL REFERENCES source_observation(id), locator TEXT NOT NULL, PRIMARY KEY(kind,row_id,observation_id,locator)) WITHOUT ROWID;
CREATE TABLE price_projection(id TEXT PRIMARY KEY REFERENCES document(id), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, row_id TEXT NOT NULL REFERENCES price_row(id), metadata INTEGER REFERENCES node(id), field_layout TEXT NOT NULL);
CREATE INDEX price_projection_lookup ON price_projection(instrument_id,trade_date,id,row_id);
CREATE INDEX price_projection_by_date ON price_projection(trade_date,instrument_id,id,row_id);
CREATE TABLE metric_projection(id TEXT PRIMARY KEY REFERENCES document(id), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, metric TEXT NOT NULL, row_id TEXT NOT NULL REFERENCES daily_metric(id), metadata INTEGER REFERENCES node(id));
CREATE TABLE input_assembly(id TEXT PRIMARY KEY REFERENCES document(id), instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, revision_reason TEXT NOT NULL);
CREATE TABLE input_field(input_id TEXT NOT NULL REFERENCES input_assembly(id), metric TEXT NOT NULL, field_document TEXT NOT NULL REFERENCES document(id), PRIMARY KEY(input_id,metric)) WITHOUT ROWID;
CREATE TABLE adjustment(id TEXT PRIMARY KEY REFERENCES document(id), instrument_id TEXT NOT NULL REFERENCES instrument(id), kind TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, factor TEXT NOT NULL, tail TEXT NOT NULL, confirmed_at TEXT NOT NULL, metadata INTEGER NOT NULL REFERENCES node(id));
CREATE TABLE event(id TEXT PRIMARY KEY REFERENCES document(id), kind TEXT NOT NULL, external_id TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES original_object(id), published_date TEXT);
CREATE TABLE validation_receipt(id TEXT PRIMARY KEY, validator_version TEXT NOT NULL, input_sha256 TEXT NOT NULL, checked_at TEXT NOT NULL, result TEXT NOT NULL CHECK(result='passed'), details TEXT NOT NULL REFERENCES document(id));
CREATE TABLE publication(id TEXT PRIMARY KEY REFERENCES document(id), domain_id TEXT NOT NULL REFERENCES domain(id), subject TEXT NOT NULL, sequence INTEGER NOT NULL CHECK(sequence>=0), base_publication TEXT REFERENCES publication(id), coverage_start TEXT, coverage_end TEXT, legacy_status TEXT NOT NULL, validation_id TEXT NOT NULL REFERENCES validation_receipt(id), UNIQUE(domain_id,subject,sequence));
CREATE TABLE publication_row(publication_id TEXT NOT NULL REFERENCES publication(id), row_kind TEXT NOT NULL, instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, metric TEXT NOT NULL DEFAULT '', projection_id TEXT REFERENCES document(id), PRIMARY KEY(publication_id,row_kind,instrument_id,trade_date,metric)) WITHOUT ROWID;
CREATE INDEX publication_row_by_day ON publication_row(trade_date,row_kind,instrument_id,publication_id);
CREATE TABLE current_row(domain_id TEXT NOT NULL REFERENCES domain(id), subject TEXT NOT NULL, binding TEXT NOT NULL, row_kind TEXT NOT NULL, instrument_id TEXT NOT NULL REFERENCES instrument(id), trade_date TEXT NOT NULL, metric TEXT NOT NULL DEFAULT '', projection_id TEXT NOT NULL REFERENCES document(id), PRIMARY KEY(domain_id,subject,binding,row_kind,instrument_id,trade_date,metric)) WITHOUT ROWID;
CREATE INDEX current_row_by_date ON current_row(trade_date,row_kind,instrument_id,projection_id);
CREATE TABLE publication_binding(publication_id TEXT NOT NULL REFERENCES publication(id), role TEXT NOT NULL, bound_id TEXT NOT NULL REFERENCES publication(id), PRIMARY KEY(publication_id,role)) WITHOUT ROWID;
CREATE TABLE publication_observation(publication_id TEXT NOT NULL REFERENCES publication(id), observation_id TEXT NOT NULL REFERENCES document(id), first_observation INTEGER NOT NULL CHECK(first_observation IN(0,1)), PRIMARY KEY(publication_id,observation_id)) WITHOUT ROWID;
CREATE TABLE current_publication(domain_id TEXT NOT NULL REFERENCES domain(id), subject TEXT NOT NULL, binding TEXT NOT NULL, publication_id TEXT NOT NULL REFERENCES publication(id), observation_id TEXT REFERENCES document(id), metadata TEXT REFERENCES document(id), PRIMARY KEY(domain_id,subject,binding)) WITHOUT ROWID;
CREATE TABLE legacy_id_map(domain_id TEXT NOT NULL REFERENCES domain(id), old_id TEXT NOT NULL, kind TEXT NOT NULL, target_id TEXT NOT NULL REFERENCES document(id), status TEXT NOT NULL, PRIMARY KEY(domain_id,old_id,kind)) WITHOUT ROWID;
CREATE TABLE journal_revision(id TEXT PRIMARY KEY, domain_id TEXT NOT NULL REFERENCES domain(id), journal_key TEXT NOT NULL, previous TEXT REFERENCES journal_revision(id), value_document TEXT NOT NULL REFERENCES document(id));
CREATE TABLE journal_head(domain_id TEXT NOT NULL REFERENCES domain(id), journal_key TEXT NOT NULL, revision_id TEXT NOT NULL REFERENCES journal_revision(id), PRIMARY KEY(domain_id,journal_key)) WITHOUT ROWID;
CREATE TABLE operation(domain_id TEXT NOT NULL REFERENCES domain(id), request_id TEXT NOT NULL, revision TEXT NOT NULL REFERENCES document(id), state TEXT NOT NULL, publication_id TEXT REFERENCES publication(id), PRIMARY KEY(domain_id,request_id)) WITHOUT ROWID;
CREATE TABLE budget_scope(domain_id TEXT NOT NULL REFERENCES domain(id), scope_id TEXT NOT NULL, grant_id TEXT, journal_key TEXT NOT NULL, PRIMARY KEY(domain_id,scope_id)) WITHOUT ROWID;
CREATE TABLE attempt(domain_id TEXT NOT NULL REFERENCES domain(id), scope_id TEXT NOT NULL, attempt_id TEXT NOT NULL, revision TEXT NOT NULL REFERENCES document(id), PRIMARY KEY(domain_id,scope_id,attempt_id)) WITHOUT ROWID;
CREATE TABLE state(domain_id TEXT NOT NULL REFERENCES domain(id), key TEXT NOT NULL, revision TEXT NOT NULL REFERENCES document(id), PRIMARY KEY(domain_id,key)) WITHOUT ROWID;
CREATE TABLE historical_archive(id TEXT PRIMARY KEY, category TEXT NOT NULL, byte_length INTEGER NOT NULL, manifest_sha256 TEXT NOT NULL, location TEXT NOT NULL);
CREATE TABLE migration(id TEXT PRIMARY KEY, source_manifest_sha256 TEXT NOT NULL UNIQUE, state TEXT NOT NULL CHECK(state IN('preparing','verified')), started_at TEXT NOT NULL, verified_at TEXT);
CREATE TABLE migration_object(migration_id TEXT NOT NULL REFERENCES migration(id), source_root TEXT NOT NULL, source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL, disposition TEXT NOT NULL, target_id TEXT, reason TEXT NOT NULL, PRIMARY KEY(migration_id,source_root,source_path)) WITHOUT ROWID;
CREATE TABLE integrity_check(id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN('structure','full')), started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL CHECK(state IN('running','passed','failed','interrupted')), version_set TEXT NOT NULL REFERENCES document(id), details TEXT REFERENCES document(id));
CREATE TABLE integrity_health(singleton INTEGER PRIMARY KEY CHECK(singleton=1), quarantined INTEGER NOT NULL CHECK(quarantined IN(0,1)), reason TEXT, last_structure TEXT, last_full TEXT);
INSERT INTO integrity_health VALUES(1,0,NULL,NULL,NULL);
'''

# 只允许变更指针、状态和检查记录；事实、原件身份与历史依据永不原地覆盖。
for _table in ('store_identity', 'domain', 'node', 'node_edge', 'document', 'document_original', 'price_row', 'daily_metric',
               'source_price_value', 'source_price_binding', 'source_price_projection', 'source_observation', 'row_provenance', 'price_projection', 'metric_projection',
               'input_assembly', 'input_field', 'adjustment', 'event', 'validation_receipt', 'publication',
               'publication_row', 'publication_binding', 'publication_observation', 'legacy_id_map',
               'journal_revision', 'historical_archive'):
    for _action in ('UPDATE', 'DELETE'):
        SCHEMA += (f'CREATE TRIGGER immutable_{_table}_{_action.lower()} BEFORE {_action} ON {_table} '
                   "BEGIN SELECT RAISE(ABORT,'immutable_history'); END;\n")
