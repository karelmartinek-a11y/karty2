CREATE TABLE account_reservation (
    reservation TEXT PRIMARY KEY CHECK(length(reservation)>0),
    booking_reference TEXT NOT NULL CHECK(length(booking_reference)>0),
    created_at TEXT NOT NULL
) STRICT;
CREATE TABLE account_symbol (
    variable_symbol TEXT NOT NULL CHECK(length(variable_symbol)>0),
    reservation TEXT NOT NULL REFERENCES account_reservation(reservation),
    file_id TEXT NOT NULL REFERENCES source_file(id),
    import_run_id TEXT NOT NULL REFERENCES import_run(id),
    sheet TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    PRIMARY KEY(variable_symbol,reservation)
) STRICT;
CREATE TRIGGER account_reservation_update BEFORE UPDATE ON account_reservation BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER account_reservation_delete BEFORE DELETE ON account_reservation BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER account_symbol_update BEFORE UPDATE ON account_symbol BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
CREATE TRIGGER account_symbol_delete BEFORE DELETE ON account_symbol BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
DELETE FROM secret;
