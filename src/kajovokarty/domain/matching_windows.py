"""Czech business calendar and bounded, unambiguous sum matching."""
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from itertools import combinations


@lru_cache(maxsize=128)
def holidays(year):
    # Gregorian Easter (Meeus/Jones/Butcher).
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    easter = date(year, n // 31, n % 31 + 1)
    fixed = {(1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28),
             (10, 28), (11, 17), (12, 24), (12, 25), (12, 26)}
    return frozenset({date(year, month, day) for month, day in fixed}
                     | {easter + timedelta(days=1)}
                     | ({easter - timedelta(days=2)} if year >= 2016 else set()))


@lru_cache(maxsize=32768)
def business_days(a, b):
    start, end = sorted((date.fromisoformat(a[:10]), date.fromisoformat(b[:10])))
    result = 0
    while start < end:
        start += timedelta(days=1)
        result += start.weekday() < 5 and start not in holidays(start.year)
    return result


def match_date(row):
    value = row['payload'].get('departure') if row['kind'] == 'BOOKING' else row['local_date']
    return value[:10] if value else None


def within(rows, window):
    dates = [match_date(row) for row in rows]
    if not dates or None in dates:
        return False
    return (min(dates) == max(dates) if window == 0
            else business_days(min(dates), max(dates)) <= window)


def compatible(a, b):
    if a['kind'] != 'CASHBOOK_CARD':
        a, b = b, a
    if b['kind'] != 'BANK_CARD':
        return True
    vs = a['payload'].get('variable_symbol')
    bankvs = {b['payload'].get(k) for k in ('variable_symbol', 'variable_symbol_2')} - {None, ''}
    return not (vs and bankvs and vs not in bankvs)


def cash_reversals(rows, pulse=lambda: None):
    candidates = []
    for index, (a, b) in enumerate(combinations(rows, 2)):
        if index % 1024 == 0:
            pulse()
        if a['kind'] != 'CASHBOOK_CARD' or b['kind'] != 'CASHBOOK_CARD':
            continue
        if (a['currency'] == b['currency']
                and a['signed_amount_minor'] == -b['signed_amount_minor']
                and a['signed_amount_minor'] != 0
                and bool(a['payload'].get('storno_marker')) != bool(b['payload'].get('storno_marker'))
                and abs((date.fromisoformat(a['local_date']) - date.fromisoformat(b['local_date'])).days) <= 2):
            candidates.append(frozenset((a['id'], b['id'])))
    # A duplicate with more possible partners remains manual, as for bank reversals.
    return candidates


def sum_candidates(rows, window, max_size=6, max_items=40, max_states=100000, pulse=lambda: None, search_progress=lambda states: None):
    """Return disjoint sums, ambiguous IDs and incomplete component IDs.

    Overlapping balanced subsets can be collapsed only if their complete union
    also balances and fits the window. Never select a subset by iteration order.
    """
    buckets = defaultdict(list)
    for row in rows:
        if match_date(row) and row['signed_amount_minor']:
            buckets[(row['currency'], row['signed_amount_minor'] > 0)].append(row)
    accepted, ambiguous, blocked = [], set(), set()

    def valid(items):
        cash = [r for r in items if r['kind'] == 'CASHBOOK_CARD']
        other = [r for r in items if r['kind'] != 'CASHBOOK_CARD']
        return (cash and other and within(items, window)
                and sum(r['signed_amount_minor'] for r in cash) == sum(r['signed_amount_minor'] for r in other)
                and all(compatible(a, b) for a in cash for b in other))

    for bucket in buckets.values():
        lookup = {r['id']: r for r in bucket}
        adjacency = {r['id']: set() for r in bucket}
        for a, b in combinations(bucket, 2):
            pulse()
            if ((a['kind'] == 'CASHBOOK_CARD') != (b['kind'] == 'CASHBOOK_CARD')
                    and within([a, b], window) and compatible(a, b)):
                adjacency[a['id']].add(b['id'])
                adjacency[b['id']].add(a['id'])
        remaining = set(lookup)
        while remaining:
            todo, component = [min(remaining)], set()
            while todo:
                identity = todo.pop()
                if identity in component:
                    continue
                component.add(identity)
                todo.extend(adjacency[identity] - component)
            remaining -= component
            items = [lookup[i] for i in sorted(component)]
            if len(component) < 2:
                continue
            if len(component) > max_items:
                blocked.update(component)
                continue
            if valid(items):
                accepted.append(frozenset(component))
                continue
            candidates, states, limited = [], 0, False
            search_progress(0)
            for size in range(2, min(max_size, len(items)) + 1):
                for subset in combinations(items, size):
                    states += 1
                    if states % 256 == 0:
                        pulse()
                        search_progress(states)
                    if states > max_states:
                        limited = True
                        break
                    ids = frozenset(r['id'] for r in subset)
                    if any(previous < ids for previous in candidates):
                        continue
                    if valid(subset):
                        candidates.append(ids)
                if limited:
                    break
            search_progress(states)
            if limited:
                blocked.update(component)
                continue
            while candidates:
                union = set(candidates.pop())
                while True:
                    overlaps = [c for c in candidates if c & union]
                    if not overlaps:
                        break
                    for candidate in overlaps:
                        union.update(candidate)
                        candidates.remove(candidate)
                if valid([lookup[i] for i in union]):
                    accepted.append(frozenset(union))
                else:
                    ambiguous.update(union)
    return accepted, ambiguous, blocked
