-- Schema-2-compatible query-plan correction. Keep all publication guards.
DROP TRIGGER IF EXISTS publish_closed_graph;
CREATE TRIGGER publish_closed_graph BEFORE UPDATE OF state ON helper_generation
WHEN NEW.state IN ('SEALED','PUBLISHED') BEGIN
 SELECT CASE WHEN EXISTS(
  SELECT 1 FROM helper_link l
  JOIN helper_current a ON a.context_id=l.context_id AND a.generation_id=l.generation_id AND a.resource_type=l.from_type AND a.external_id=l.from_id
  JOIN helper_current b ON b.context_id=l.context_id AND b.generation_id=l.generation_id AND b.resource_type=l.to_type AND b.external_id=l.to_id
  WHERE l.context_id=NEW.context_id AND l.generation_id=NEW.id AND l.active=1
    AND (l.complete!=1 OR a.active!=1 OR a.complete!=1 OR b.active!=1 OR b.complete!=1)
 ) THEN RAISE(ABORT,'HELPER_EDGE_INCOMPLETE') END;
 SELECT CASE WHEN EXISTS(
  WITH RECURSIVE reachable(t,i) AS MATERIALIZED (
   SELECT resource_type,external_id FROM helper_current
   WHERE context_id=NEW.context_id AND generation_id=NEW.id AND root_observed=1 AND active=1
   UNION
   SELECT l.to_type,l.to_id FROM reachable r CROSS JOIN helper_link l
   WHERE l.from_type=r.t AND l.from_id=r.i
     AND l.context_id=NEW.context_id AND l.generation_id=NEW.id AND l.active=1 AND l.complete=1
  )
  SELECT 1 FROM helper_current h LEFT JOIN reachable r ON r.t=h.resource_type AND r.i=h.external_id
  WHERE h.context_id=NEW.context_id AND h.generation_id=NEW.id AND h.active=1 AND r.t IS NULL
 ) THEN RAISE(ABORT,'NO_ACTIVE_ROOT_PATH') END;
 SELECT CASE WHEN NEW.kind='FULL' AND EXISTS(
  SELECT 1 FROM (SELECT 'invoice' kind UNION ALL SELECT 'reservation') k
  WHERE NOT EXISTS(SELECT 1 FROM sync_coverage
   WHERE context_id=NEW.context_id AND generation_id=NEW.id AND resource_type=k.kind
     AND complete=1 AND range_start<=json_extract(NEW.plan_json,'$.start')
     AND range_end>=json_extract(NEW.plan_json,'$.end'))
 ) THEN RAISE(ABORT,'COVERAGE_INCOMPLETE') END;
END;
