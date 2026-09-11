-- Idempotent data migration; preserve an explicitly configured start date.
INSERT INTO setting(key,value_json,revision)
VALUES('sync.start_date','"2026-01-01"',1)
ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,revision=setting.revision+1
WHERE setting.value_json IN ('""', 'null');
