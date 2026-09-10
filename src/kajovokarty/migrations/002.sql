-- Additive migration: immutable financial meanings are never rewritten.
ALTER TABLE cashbook_detail ADD COLUMN issued_local TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.issued_local')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN movement TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.movement')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN label TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.label')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN client TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.client')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN income_minor INTEGER GENERATED ALWAYS AS (json_extract(payload_json,'$.income_minor')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN expense_minor INTEGER GENERATED ALWAYS AS (json_extract(payload_json,'$.expense_minor')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN currency TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.currency')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN payment_form TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.payment_form')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN variable_symbol TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.variable_symbol')) VIRTUAL;
ALTER TABLE cashbook_detail ADD COLUMN issued_by TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.issued_by')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN pos_id TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.pos_id')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN occurred_local TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.occurred_local')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN server_local TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.server_local')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN booked_date TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.booked_date')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN signed_amount_minor INTEGER GENERATED ALWAYS AS (json_extract(payload_json,'$.signed_amount_minor')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN cashback_minor INTEGER GENERATED ALWAYS AS (json_extract(payload_json,'$.cashback_minor')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN tip_minor INTEGER GENERATED ALWAYS AS (json_extract(payload_json,'$.tip_minor')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN currency TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.currency')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN arn TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.arn')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN dcc TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.dcc')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN masked_account TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.masked_account')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN authorization_code TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.authorization_code')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN variable_symbol TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.variable_symbol')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN variable_symbol_2 TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.variable_symbol_2')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN issuer TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.issuer')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN entry_method TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.entry_method')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN merchant TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.merchant')) VIRTUAL;
ALTER TABLE bank_detail ADD COLUMN merchant_address TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.merchant_address')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN invoice_type TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.invoice_type')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN arrival TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.arrival')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN departure TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.departure')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN guest_name TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.guest_name')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN provider TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.provider')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN reservation_status TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.reservation_status')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN currency TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.currency')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN payment_status TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.payment_status')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN signed_amount_minor INTEGER GENERATED ALWAYS AS (json_extract(payload_json,'$.signed_amount_minor')) VIRTUAL;
ALTER TABLE booking_detail ADD COLUMN payout_date TEXT GENERATED ALWAYS AS (json_extract(payload_json,'$.payout_date')) VIRTUAL;
CREATE TABLE domain_clock(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL) STRICT;
INSERT INTO domain_clock VALUES(1,0);
CREATE TRIGGER clock_financial_source_INSERT AFTER INSERT ON financial_source BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_financial_source_UPDATE AFTER UPDATE ON financial_source BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_financial_source_DELETE AFTER DELETE ON financial_source BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_cashbook_detail_INSERT AFTER INSERT ON cashbook_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_cashbook_detail_UPDATE AFTER UPDATE ON cashbook_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_cashbook_detail_DELETE AFTER DELETE ON cashbook_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_bank_detail_INSERT AFTER INSERT ON bank_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_bank_detail_UPDATE AFTER UPDATE ON bank_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_bank_detail_DELETE AFTER DELETE ON bank_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_booking_detail_INSERT AFTER INSERT ON booking_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_booking_detail_UPDATE AFTER UPDATE ON booking_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_booking_detail_DELETE AFTER DELETE ON booking_detail BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_work_object_INSERT AFTER INSERT ON work_object BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_work_object_UPDATE AFTER UPDATE ON work_object BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_work_object_DELETE AFTER DELETE ON work_object BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_membership_INSERT AFTER INSERT ON membership BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_membership_UPDATE AFTER UPDATE ON membership BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_membership_DELETE AFTER DELETE ON membership BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_reconciliation_group_INSERT AFTER INSERT ON reconciliation_group BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_reconciliation_group_UPDATE AFTER UPDATE ON reconciliation_group BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_reconciliation_group_DELETE AFTER DELETE ON reconciliation_group BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE INDEX work_active_type ON work_object(lifecycle,type,id);
CREATE INDEX occurrence_source ON source_occurrence(source_id);
CREATE INDEX helper_search_scope ON helper_current(context_id,generation_id,active,resource_type);
CREATE TRIGGER generation_context_INSERT BEFORE INSERT ON helper_generation BEGIN
 SELECT CASE WHEN NEW.predecessor_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM helper_generation WHERE id=NEW.predecessor_id AND context_id=NEW.context_id AND state='PUBLISHED') THEN RAISE(ABORT,'GENERATION_CONTEXT_MISMATCH') END;
 SELECT CASE WHEN NEW.state NOT IN ('STAGING','SEALED','PUBLISHED','ABORTED') OR NEW.kind NOT IN ('FULL','DETAIL') THEN RAISE(ABORT,'GENERATION_INVALID') END;
END;
CREATE TRIGGER current_snapshot_identity_INSERT BEFORE INSERT ON helper_current BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_snapshot WHERE id=NEW.snapshot_id AND context_id=NEW.context_id AND resource_type=NEW.resource_type AND external_id=NEW.external_id AND projection_kind='MERGED_ENTITY') THEN RAISE(ABORT,'SNAPSHOT_IDENTITY_MISMATCH') END;
 SELECT CASE WHEN NEW.revision<1 OR NEW.active NOT IN(0,1) OR NEW.complete NOT IN(0,1) OR NEW.root_observed NOT IN(0,1) THEN RAISE(ABORT,'HELPER_INVALID') END;
END;
CREATE TRIGGER reference_identity_INSERT BEFORE INSERT ON helper_reference BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_current WHERE context_id=NEW.context_id AND generation_id=NEW.generation_id AND resource_type='reservation' AND external_id=NEW.reservation_id AND snapshot_id=NEW.snapshot_id) THEN RAISE(ABORT,'REFERENCE_CONTEXT_MISMATCH') END;
END;
CREATE TRIGGER override_context_INSERT BEFORE INSERT ON helper_override BEGIN
 SELECT CASE WHEN NEW.accepted NOT IN(0,1) OR NEW.active NOT IN(0,1) OR NEW.revision<1 OR (NEW.accepted=0 AND NEW.candidate IS NOT NULL) THEN RAISE(ABORT,'OVERRIDE_INVALID') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_current WHERE context_id=NEW.context_id AND resource_type='reservation' AND external_id=NEW.reservation_id) THEN RAISE(ABORT,'REFERENCE_CONTEXT_MISMATCH') END;
END;
CREATE TRIGGER compatibility_context_INSERT BEFORE INSERT ON api_compatibility_run WHEN NEW.helper_generation_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_generation WHERE id=NEW.helper_generation_id AND context_id=NEW.context_id) THEN RAISE(ABORT,'GENERATION_CONTEXT_MISMATCH') END;
END;
CREATE TRIGGER generation_context_UPDATE BEFORE UPDATE ON helper_generation BEGIN
 SELECT CASE WHEN NEW.predecessor_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM helper_generation WHERE id=NEW.predecessor_id AND context_id=NEW.context_id AND state='PUBLISHED') THEN RAISE(ABORT,'GENERATION_CONTEXT_MISMATCH') END;
 SELECT CASE WHEN NEW.state NOT IN ('STAGING','SEALED','PUBLISHED','ABORTED') OR NEW.kind NOT IN ('FULL','DETAIL') THEN RAISE(ABORT,'GENERATION_INVALID') END;
END;
CREATE TRIGGER current_snapshot_identity_UPDATE BEFORE UPDATE ON helper_current BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_snapshot WHERE id=NEW.snapshot_id AND context_id=NEW.context_id AND resource_type=NEW.resource_type AND external_id=NEW.external_id AND projection_kind='MERGED_ENTITY') THEN RAISE(ABORT,'SNAPSHOT_IDENTITY_MISMATCH') END;
 SELECT CASE WHEN NEW.revision<1 OR NEW.active NOT IN(0,1) OR NEW.complete NOT IN(0,1) OR NEW.root_observed NOT IN(0,1) THEN RAISE(ABORT,'HELPER_INVALID') END;
END;
CREATE TRIGGER reference_identity_UPDATE BEFORE UPDATE ON helper_reference BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_current WHERE context_id=NEW.context_id AND generation_id=NEW.generation_id AND resource_type='reservation' AND external_id=NEW.reservation_id AND snapshot_id=NEW.snapshot_id) THEN RAISE(ABORT,'REFERENCE_CONTEXT_MISMATCH') END;
END;
CREATE TRIGGER override_context_UPDATE BEFORE UPDATE ON helper_override BEGIN
 SELECT CASE WHEN NEW.accepted NOT IN(0,1) OR NEW.active NOT IN(0,1) OR NEW.revision<1 OR (NEW.accepted=0 AND NEW.candidate IS NOT NULL) THEN RAISE(ABORT,'OVERRIDE_INVALID') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_current WHERE context_id=NEW.context_id AND resource_type='reservation' AND external_id=NEW.reservation_id) THEN RAISE(ABORT,'REFERENCE_CONTEXT_MISMATCH') END;
END;
CREATE TRIGGER compatibility_context_UPDATE BEFORE UPDATE ON api_compatibility_run WHEN NEW.helper_generation_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_generation WHERE id=NEW.helper_generation_id AND context_id=NEW.context_id) THEN RAISE(ABORT,'GENERATION_CONTEXT_MISMATCH') END;
END;
CREATE TRIGGER sealed_new_helper_current BEFORE UPDATE ON helper_current WHEN (SELECT state FROM helper_generation WHERE id=NEW.generation_id) IN ('SEALED','PUBLISHED') BEGIN SELECT RAISE(ABORT,'GENERATION_IMMUTABLE'); END;
CREATE TRIGGER sealed_new_helper_link BEFORE UPDATE ON helper_link WHEN (SELECT state FROM helper_generation WHERE id=NEW.generation_id) IN ('SEALED','PUBLISHED') BEGIN SELECT RAISE(ABORT,'GENERATION_IMMUTABLE'); END;
CREATE TRIGGER sealed_new_helper_reference BEFORE UPDATE ON helper_reference WHEN (SELECT state FROM helper_generation WHERE id=NEW.generation_id) IN ('SEALED','PUBLISHED') BEGIN SELECT RAISE(ABORT,'GENERATION_IMMUTABLE'); END;
CREATE TRIGGER sealed_new_sync_coverage BEFORE UPDATE ON sync_coverage WHEN (SELECT state FROM helper_generation WHERE id=NEW.generation_id) IN ('SEALED','PUBLISHED') BEGIN SELECT RAISE(ABORT,'GENERATION_IMMUTABLE'); END;
CREATE TRIGGER publish_closed_graph BEFORE UPDATE OF state ON helper_generation WHEN NEW.state IN ('SEALED','PUBLISHED') BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM helper_link l JOIN helper_current a ON a.context_id=l.context_id AND a.generation_id=l.generation_id AND a.resource_type=l.from_type AND a.external_id=l.from_id JOIN helper_current b ON b.context_id=l.context_id AND b.generation_id=l.generation_id AND b.resource_type=l.to_type AND b.external_id=l.to_id WHERE l.context_id=NEW.context_id AND l.generation_id=NEW.id AND l.active=1 AND (l.complete!=1 OR a.active!=1 OR a.complete!=1 OR b.active!=1 OR b.complete!=1)) THEN RAISE(ABORT,'HELPER_EDGE_INCOMPLETE') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM helper_current h WHERE h.context_id=NEW.context_id AND h.generation_id=NEW.id AND h.active=1 AND NOT EXISTS(WITH RECURSIVE reachable(t,i) AS (SELECT resource_type,external_id FROM helper_current WHERE context_id=NEW.context_id AND generation_id=NEW.id AND root_observed=1 AND active=1 UNION SELECT l.to_type,l.to_id FROM helper_link l JOIN reachable r ON l.from_type=r.t AND l.from_id=r.i WHERE l.context_id=NEW.context_id AND l.generation_id=NEW.id AND l.active=1 AND l.complete=1) SELECT 1 FROM reachable WHERE t=h.resource_type AND i=h.external_id)) THEN RAISE(ABORT,'NO_ACTIVE_ROOT_PATH') END;
 SELECT CASE WHEN NEW.kind='FULL' AND EXISTS(SELECT 1 FROM (SELECT 'invoice' kind UNION ALL SELECT 'reservation') k WHERE NOT EXISTS(SELECT 1 FROM sync_coverage WHERE context_id=NEW.context_id AND generation_id=NEW.id AND resource_type=k.kind AND complete=1 AND range_start<=json_extract(NEW.plan_json,'$.start') AND range_end>=json_extract(NEW.plan_json,'$.end'))) THEN RAISE(ABORT,'COVERAGE_INCOMPLETE') END;
END;
CREATE TRIGGER state_pointer_guard BEFORE UPDATE ON helper_state BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM helper_context WHERE id=NEW.context_id AND status='CURRENT' AND credential_revision=NEW.credential_revision) THEN RAISE(ABORT,'API_CONTEXT_CHANGED') END;
 SELECT CASE WHEN NEW.published_generation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM helper_generation WHERE id=NEW.published_generation_id AND context_id=NEW.context_id AND state='PUBLISHED') THEN RAISE(ABORT,'GENERATION_NOT_PUBLISHED') END;
 SELECT CASE WHEN NEW.status='READY' AND NEW.published_generation_id IS NULL THEN RAISE(ABORT,'GENERATION_NOT_PUBLISHED') END;
END;

CREATE TABLE source_search(source_id TEXT PRIMARY KEY REFERENCES financial_source(id),local_search_text TEXT NOT NULL) STRICT;
INSERT INTO source_search SELECT id,kk_search_normalize(canonical_json||' '||id) FROM financial_source;
CREATE TRIGGER source_search_insert AFTER INSERT ON financial_source BEGIN
 INSERT INTO source_search VALUES(NEW.id,kk_search_normalize(NEW.canonical_json||' '||NEW.id));
END;
CREATE TRIGGER source_work_guard_insert BEFORE INSERT ON work_object WHEN NEW.type='SOURCE' BEGIN
 SELECT CASE WHEN NEW.lifecycle!='ACTIVE' OR NOT EXISTS(SELECT 1 FROM financial_source WHERE id=NEW.source_id AND currency=NEW.currency) THEN RAISE(ABORT,'SOURCE_INVALID') END;
END;
CREATE TRIGGER work_identity_guard BEFORE UPDATE ON work_object BEGIN
 SELECT CASE WHEN NEW.id!=OLD.id OR NEW.type!=OLD.type OR NEW.source_id IS NOT OLD.source_id OR NEW.currency!=OLD.currency THEN RAISE(ABORT,'WORK_IDENTITY_IMMUTABLE') END;
 SELECT CASE WHEN NEW.type='SOURCE' AND NEW.lifecycle!='ACTIVE' THEN RAISE(ABORT,'SOURCE_INVALID') END;
END;
CREATE TRIGGER cashbook_type_guard BEFORE INSERT ON cashbook_detail BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM financial_source WHERE id=NEW.source_id AND kind='CASHBOOK_CARD' AND canonical_json=NEW.payload_json) THEN RAISE(ABORT,'SOURCE_SUBTYPE_INVALID') END;
END;
CREATE TRIGGER bank_type_guard BEFORE INSERT ON bank_detail BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM financial_source WHERE id=NEW.source_id AND kind='BANK_CARD' AND canonical_json=NEW.payload_json) THEN RAISE(ABORT,'SOURCE_SUBTYPE_INVALID') END;
END;
CREATE TRIGGER booking_type_guard BEFORE INSERT ON booking_detail BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM financial_source WHERE id=NEW.source_id AND kind='BOOKING' AND canonical_json=NEW.payload_json) THEN RAISE(ABORT,'SOURCE_SUBTYPE_INVALID') END;
END;
CREATE TABLE work_reason(object_id TEXT PRIMARY KEY REFERENCES work_object(id),code TEXT NOT NULL,domain_revision INTEGER NOT NULL,helper_revision INTEGER NOT NULL,settings_revision INTEGER NOT NULL) STRICT;
CREATE TRIGGER clock_suppression_insert AFTER INSERT ON auto_suppression BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER clock_suppression_update AFTER UPDATE ON auto_suppression BEGIN UPDATE domain_clock SET revision=revision+1 WHERE id=1; END;

-- Existing evidence stays immutable; revalidate helpers after the corrected wire/parser implementation.
UPDATE helper_state SET status='STALE',failure_code='SCHEMA_UPGRADE',revision=revision+1 WHERE status='READY';
