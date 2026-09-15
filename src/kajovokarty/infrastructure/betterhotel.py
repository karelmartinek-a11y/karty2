"""Historical endpoint identities; online transport has been removed."""

from __future__ import annotations
from kajovokarty.domain.core import AppError, digest

BASE = "https://api.better-hotel.com/api/connector/v/1"
TEMPLATES = [
    "/currency",
    "/invoice",
    "/invoice/{invoice_id}",
    "/reservation",
    "/reservation/{reservation_id}",
    "/reservation/{reservation_id}/invoice",
    "/reservation/{reservation_id}/bill",
    "/bill/{bill_id}",
    "/bill/{bill_id}/bill-item",
    "/bill-item/{item_id}",
    "/reservation/{reservation_id}/security-deposit",
    "/financial-stats",
]


RESERVATION_EXPAND = [
    ("expand[]", "reservation_source"),
    ("expand[]", "reservation_note"),
]


def request_shape(template):
    """Projection identity excludes dates, cursor and count (SSOT 8.3)."""
    return digest(
        {
            "endpoint_template": template,
            "expand": [v for _, v in RESERVATION_EXPAND]
            if template in ("/reservation", "/reservation/{reservation_id}")
            else [],
            "filters": [],
        }
    )


class BetterHotelClient:
    """Compatibility tombstone: live API access was replaced by the Accounts import."""

    def __init__(self, *args, **kwargs):
        raise AppError("API_REMOVED", "BetterHotel API bylo odstraněno. Použijte ruční import Účty (XLS).")
