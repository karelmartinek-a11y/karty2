import pytest
from kajovokarty.domain.helpers import normalize_entity
from kajovokarty.domain.core import AppError
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from test_api import client

SOURCE_ID = 'e67d16b9-64ec-ac15-cd7d-06602e308dd2'


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('source', [SOURCE_ID, None, {'uuid': SOURCE_ID.upper()}, {'source_id': SOURCE_ID}])
def test_observed_source_alias(source, reverse):
    fields = [('source', source), ('reservation_source', {'id': SOURCE_ID, 'name': 'Přímá rezervace'})]
    raw = dict([('id', 'R1')] + (fields[::-1] if reverse else fields))
    assert normalize_entity('reservation', raw, {})['reservation_source'] == {'id': SOURCE_ID, 'name': 'Přímá rezervace'}


def test_conflicting_source_is_rejected():
    with pytest.raises(AppError) as exc:
        normalize_entity('reservation', {'id': 'R1', 'source': SOURCE_ID,
            'reservation_source': {'id': '00000000-0000-0000-0000-000000000000'}}, {})
    assert exc.value.code == 'API_SNAPSHOT_CONFLICT'
    assert exc.value.details['field'] == 'reservation_source.id'


def test_internal_id_alias_conflict():
    with pytest.raises(AppError):
        normalize_entity('reservation', {'id': 'R1', 'source': {'id': '7', 'uuid': '8'}}, {})


def test_both_null():
    assert normalize_entity('reservation', {'id': 'R1', 'source': None, 'reservation_source': None}, {})['reservation_source'] is None


def test_observed_invoice_empty_uuid_alias():
    assert normalize_entity('invoice', {'id': '722f61dc-1e23-5f63-587f-c6c414ab1be5', 'uuid': ''}, {})['id'] == '722f61dc-1e23-5f63-587f-c6c414ab1be5'


@pytest.mark.parametrize('archived', [False, True])
def test_bill_item_archive_flag(archived):
    raw = {'id': 'b17440ca-5c3e-0095-caaa-3b84c362df1c',
           'archived': archived, 'date': '2026-09-10T19:54:37+00:00'}
    result = normalize_entity('bill_item', raw, {})
    assert result['archived'] is archived
    assert result['date'] == '2026-09-10T19:54:37.000000Z'


def test_observed_security_deposit_breakdown():
    raw = {'id': '60ca8d1e-eddf-e926-0cd4-19b8819023b3', 'items': [], 'deposit': []}
    assert normalize_entity('security_deposit', raw, {}) == raw


@pytest.mark.parametrize('raw', [
    {'id': 'I1', 'uuid': None}, {'uuid': 'I1', 'id': ''},
    {'id': 'I1', 'uuid': 'I1'},
])
def test_known_entity_id_survives_empty_alias(raw):
    assert normalize_entity('invoice', raw, {})['id'] == 'I1'


def test_entity_identity_conflict_is_not_suppressed():
    with pytest.raises(AppError) as exc:
        normalize_entity('invoice', {'id': 'I1', 'uuid': 'I2'}, {})
    assert exc.value.code == 'API_SNAPSHOT_CONFLICT'


def test_real_source_name_conflict_is_not_suppressed():
    with pytest.raises(AppError) as exc:
        normalize_entity('reservation', {'id': 'R1',
            'source': {'id': SOURCE_ID, 'name': 'A'},
            'reservation_source': {'id': SOURCE_ID, 'name': 'B'}}, {})
    assert exc.value.details['field'] == 'reservation_source.name'


def test_full_sync_with_observed_alias_shape(db, wire):
    # Preserve fixture's channel semantics; use the exact live UUID/scalar shape.
    for endpoint in ('/reservation', '/reservation/R1'):
        data = wire[endpoint]['data']
        for row in data if isinstance(data, list) else [data]:
            if row.get('id') != 'R1':
                continue
            row['source'] = SOURCE_ID
            row.setdefault('reservation_source', {'name': 'Booking.com'})['id'] = SOURCE_ID
    for endpoint, body in wire.items():
        data = body.get('data')
        if isinstance(data, dict) and endpoint.startswith('/invoice/'):
            data['uuid'] = ''
        if isinstance(data, dict) and endpoint.startswith('/bill-item/'):
            data['archived'] = False
    http = client(wire)
    try:
        sync = SyncService(db, SettingsService(db))
        result = sync.full(http, scope=('2026-09-07', '2026-09-08'))
        assert result['status'] == sync.state()['status'] == 'READY'
        with db.connect() as c:
            assert c.execute('SELECT state FROM operation WHERE id=?', (result['operation_id'],)).fetchone()[0] == 'COMPLETED'
    finally:
        http.close()
