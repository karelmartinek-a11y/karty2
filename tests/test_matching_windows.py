import json

import pytest

from kajovokarty.domain.matching_windows import business_days, sum_candidates, cash_reversals
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.work import WorkService
from test_acceptance_traces import seed


def row(identity, kind, amount, day='2026-05-23', currency='EUR', storno=False):
    return dict(id=identity, kind=kind, signed_amount_minor=amount, currency=currency,
                local_date=day, payload={'departure': day, 'storno_marker': storno})


@pytest.mark.parametrize('a,b,expected', [
    ('2026-06-12', '2026-06-16', 2),
    ('2026-06-12', '2026-06-17', 3),
    ('2026-04-02', '2026-04-07', 1),
    ('2026-12-23', '2026-12-29', 2),
    ('2026-12-31', '2027-01-05', 2),
    ('2026-05-07', '2026-05-11', 1),
])
def test_czech_business_days_are_symmetric(a, b, expected):
    assert business_days(a, b) == business_days(b, a) == expected


def test_screenshot_four_members():
    rows = [row('c1', 'CASHBOOK_CARD', 16265), row('c2', 'CASHBOOK_CARD', 16265),
            row('b1', 'BANK_CARD', 16265), row('b2', 'BANK_CARD', 16265)]
    assert sum_candidates(rows, 0) == ([frozenset(r['id'] for r in rows)], set(), set())
    assert sum_candidates(list(reversed(rows)), 0) == sum_candidates(rows, 0)


@pytest.mark.parametrize('kind', ['BANK_CARD', 'BOOKING'])
def test_different_amounts_across_weekend(kind):
    rows = [row('c1', 'CASHBOOK_CARD', 10000, '2026-06-12'),
            row('c2', 'CASHBOOK_CARD', 20000, '2026-06-15'),
            row('b', kind, 30000, '2026-06-16')]
    assert sum_candidates(rows, 2)[0] == [frozenset({'c1', 'c2', 'b'})]
    assert not sum_candidates(rows, 0)[0]
    rows[-1]['local_date'] = rows[-1]['payload']['departure'] = '2026-06-17'
    assert not sum_candidates(rows, 2)[0]


def test_ambiguity_limits_and_mismatch():
    rows = [row('c1', 'CASHBOOK_CARD', 100), row('c2', 'CASHBOOK_CARD', 100), row('b', 'BANK_CARD', 100)]
    matches, ambiguous, blocked = sum_candidates(rows, 2)
    assert not matches and ambiguous == {'c1', 'c2', 'b'} and not blocked
    assert sum_candidates(rows, 2, max_states=1) == ([], set(), {'c1', 'c2', 'b'})
    assert sum_candidates(rows, 2, max_items=2) == ([], set(), {'c1', 'c2', 'b'})
    rows[-1]['signed_amount_minor'] = 201
    assert not sum_candidates(rows, 2)[0]
    rows[-1]['signed_amount_minor'] = 200
    rows[-1]['currency'] = 'CZK'
    assert not sum_candidates(rows, 2)[0]


def test_entire_balanced_component_can_exceed_combination_limit():
    rows = [row(str(i), 'CASHBOOK_CARD', 100) for i in range(7)] + [row('b', 'BANK_CARD', 700)]
    assert len(next(iter(sum_candidates(rows, 2)[0]))) == 8


def test_conflicting_terminal_vs_cannot_be_hidden_in_sum():
    rows = [row('c', 'CASHBOOK_CARD', 100), row('b', 'BANK_CARD', 100)]
    rows[0]['payload']['variable_symbol'] = '1'
    rows[1]['payload']['variable_symbol'] = '2'
    assert not sum_candidates(rows, 2)[0]


@pytest.mark.parametrize('day,marker,amount,expected', [
    ('2026-05-25', True, -100, True), ('2026-05-26', True, -100, False),
    ('2026-05-24', False, -100, False), ('2026-05-24', True, -101, False),
])
def test_cash_storno(day, marker, amount, expected):
    rows = [row('normal', 'CASHBOOK_CARD', 100), row('storno', 'CASHBOOK_CARD', amount, day, storno=marker)]
    assert bool(cash_reversals(rows)) == expected


def test_sum_persistence_undo_and_suppression(db):
    ids = {seed(db, 'CASHBOOK_CARD', amount='162.65', vs='1', minute='00'),
           seed(db, 'CASHBOOK_CARD', amount='162.65', vs='2', minute='01'),
           seed(db, 'BANK_CARD', amount='162.65', vs=None, seq='1'),
           seed(db, 'BANK_CARD', amount='162.65', vs=None, seq='2')}
    matcher = MatchingService(db, SettingsService(db))
    result = matcher.run()
    assert result['groups_by_rule'] == {'C_SUM': 1}
    with db.connect() as c:
        assert {r[0] for r in c.execute('SELECT child_id FROM membership WHERE active=1')} == ids
        evidence = json.loads(c.execute('SELECT evidence_json FROM reconciliation_group').fetchone()[0])
        assert evidence['source_totals_minor'] == {'BANK_CARD': 32530, 'CASHBOOK_CARD': 32530}
    assert matcher.run()['created_groups'] == 0
    WorkService(db).undo()
    assert matcher.run()['created_groups'] == 0
    # The old group must not be hidden inside a larger balanced group.
    seed(db, 'CASHBOOK_CARD', amount='162.65', vs='3', minute='02')
    seed(db, 'BANK_CARD', amount='162.65', vs=None, seq='3')
    assert matcher.run()['created_groups'] == 0


def test_two_business_day_pair(db):
    seed(db, 'CASHBOOK_CARD', amount='80.00', vs='1')
    seed(db, 'BANK_CARD', amount='80.00', vs=None, day='09')
    result = MatchingService(db, SettingsService(db)).run()
    assert result['groups_by_rule'] == {'C_TERMINAL': 1}


def test_no_chaining_across_longer_window():
    rows = [row('c1', 'CASHBOOK_CARD', 100, '2026-06-08'),
            row('b1', 'BANK_CARD', 100, '2026-06-10'),
            row('c2', 'CASHBOOK_CARD', 100, '2026-06-12'),
            row('b2', 'BANK_CARD', 100, '2026-06-16')]
    matches, ambiguous, blocked = sum_candidates(rows, 2)
    assert not matches and ambiguous == {r['id'] for r in rows} and not blocked


def test_old_calendar_setting_cannot_extend_new_window(db):
    with db.transaction() as c:
        c.execute("INSERT INTO setting VALUES('matching.bank_window_days','7',1)")
    seed(db, 'CASHBOOK_CARD', amount='80.00', vs='1')
    seed(db, 'BANK_CARD', amount='80.00', vs='1', day='10')
    assert MatchingService(db, SettingsService(db)).run()['created_groups'] == 0


def test_booking_reference_respects_business_window(db):
    from test_accounts import import_sample, add_references
    import_sample(db)
    add_references(db, [('20260001', 'R1', '1234567890')])
    seed(db, 'CASHBOOK_CARD')
    seed(db, 'BOOKING', departure='2026-09-10')
    assert MatchingService(db, SettingsService(db)).run()['created_groups'] == 0


def test_suppressed_pair_cannot_reappear_in_sum(db):
    seed(db, 'CASHBOOK_CARD', amount='50.00', vs='1')
    seed(db, 'BANK_CARD', amount='50.00', vs=None, seq='1')
    matcher = MatchingService(db, SettingsService(db))
    assert matcher.run()['groups_by_rule'] == {'C_TERMINAL': 1}
    WorkService(db).undo()
    seed(db, 'CASHBOOK_CARD', amount='50.00', vs='2', minute='01')
    seed(db, 'BANK_CARD', amount='50.00', vs=None, seq='2')
    assert matcher.run()['created_groups'] == 0
