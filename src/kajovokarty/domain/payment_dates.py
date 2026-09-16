"""Dates used by payment views; stored payout identities remain unchanged."""
import json
from datetime import date


def payment_date(kind, local_date, canonical_json):
    if kind != "BOOKING":
        return local_date
    value = json.loads(canonical_json).get("departure")
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        # Legacy damaged metadata must never appear as a payout date.
        return None
