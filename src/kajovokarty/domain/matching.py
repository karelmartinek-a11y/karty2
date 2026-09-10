"""Deterministic candidate enumeration, independent of database and GUI."""

from itertools import combinations
from collections import Counter, defaultdict
from datetime import date


def isolated(candidates):
    degree = Counter(i for candidate in candidates for i in candidate)
    return [
        candidate for candidate in candidates if all(degree[i] == 1 for i in candidate)
    ]


def zero_combinations(
    items, max_size=6, max_items=40, max_states=100000, pulse=None, search_progress=None
):
    if len(items) > max_items:
        return [], True, 0
    ordered = sorted(items, key=lambda r: (r["kind"], r["source_identity"]))
    found = []
    states = 1
    for k in range(2, min(max_size, len(ordered)) + 1):
        for combo in combinations(ordered, k):
            states += 1
            if states % 1024 == 0:
                if search_progress:
                    search_progress(states)
                if pulse:
                    pulse()
            if states > max_states:
                if search_progress:
                    search_progress(states)
                return [], True, states
            ids = frozenset(r["id"] for r in combo)
            if len({r["kind"] for r in combo}) < 2:
                continue
            if sum(r["contribution"] for r in combo) != 0:
                continue
            if any(prev < ids for prev in found):
                continue
            found.append(ids)
    if search_progress:
        search_progress(states)
    return found, False, states


def days(a, b):
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def bank_edges(
    cash, bank, window, strong=True, weak_allowed=None, pulse=None, track=None
):
    edges = []
    index = defaultdict(list)
    for b in bank:
        index[(b["currency"], b["signed_amount_minor"])].append(b)
    for a in track(cash) if track else cash:
        if pulse:
            pulse()
        for b in index[(a["currency"], a["signed_amount_minor"])]:
            if pulse:
                pulse()
            if (
                a["currency"] != b["currency"]
                or a["signed_amount_minor"] != b["signed_amount_minor"]
                or days(a["local_date"], b["local_date"]) > window
            ):
                continue
            vs = a["payload"].get("variable_symbol")
            bankvs = {
                b["payload"].get(k) for k in ("variable_symbol", "variable_symbol_2")
            } - {None, ""}
            if vs and bankvs and vs not in bankvs:
                continue
            proof = bool(vs and vs in bankvs)
            if proof == strong and (strong or weak_allowed(a)):
                edges.append(frozenset((a["id"], b["id"])))
    return edges


def reversals(bank, pulse=None, track=None):
    edges = []
    index = defaultdict(list)
    for b in bank:
        if b["payload"]["event_class"] == "REVERSAL":
            index[
                (b["currency"], b["payload"]["terminal_id"], b["payload"]["seq_id"])
            ].append(b)
    for a in track(bank) if track else bank:
        if pulse:
            pulse()
        if a["payload"]["event_class"] != "SALE":
            continue
        for b in index[
            (a["currency"], a["payload"]["terminal_id"], a["payload"]["seq_id"])
        ]:
            if pulse:
                pulse()
            x, y = a["payload"], b["payload"]
            if y["event_class"] != "REVERSAL" or a["currency"] != b["currency"]:
                continue
            if (
                x["terminal_id"] != y["terminal_id"]
                or x["seq_id"] != y["seq_id"]
                or a["signed_amount_minor"] != -b["signed_amount_minor"]
            ):
                continue
            if (
                y["occurred_local"] < x["occurred_local"]
                or days(x["occurred_local"], y["occurred_local"]) > 7
            ):
                continue
            if not x.get("masked_account") or not x.get("authorization_code"):
                continue
            if x["masked_account"] == y.get("masked_account") and x[
                "authorization_code"
            ] == y.get("authorization_code"):
                edges.append(frozenset((a["id"], b["id"])))
    return edges
