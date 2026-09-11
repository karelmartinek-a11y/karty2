"""Private evidence for conflicts, separate from the redacted technical log."""
import json
from kajovokarty.domain.core import AppError, digest, now, uid


def record_conflict(db, operation, kind, entity_id, template, before, after, logger=None):
    diagnostic_id = uid()
    fields = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    if not fields:
        fields = sorted(before.keys() ^ after.keys())
    folder = db.path.parent / "diagnostics" / "conflicts"
    folder.mkdir(parents=True, exist_ok=True)
    evidence = {
        "operation_id": operation, "timestamp": now(), "resource_type": kind,
        "entity_id": entity_id, "endpoint_template": template,
        "changed_fields": fields, "before_hash": digest(before), "after_hash": digest(after),
        "before": before, "after": after,
    }
    (folder / (diagnostic_id + ".json")).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if logger:
        logger.write({"error_code": "API_SNAPSHOT_CONFLICT", "correlation_id": operation,
                      "endpoint_template": template, "diagnostic_id": diagnostic_id,
                      "resource_type": kind, "changed_fields": fields})
    return AppError(
        "API_SNAPSHOT_CONFLICT", "Podklady stejné entity se liší; podrobnosti byly uloženy do diagnostiky.",
        {"diagnostic_id": diagnostic_id, "resource_type": kind,
         "endpoint_template": template, "changed_fields": fields},
    )
