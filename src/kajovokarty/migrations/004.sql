CREATE TRIGGER IF NOT EXISTS membership_source_only_INSERT BEFORE INSERT ON membership WHEN NEW.active=1 BEGIN
    SELECT CASE WHEN EXISTS(
        SELECT 1 FROM work_object child
        WHERE child.id=NEW.child_id AND child.type!='SOURCE'
    ) THEN RAISE(ABORT,'GROUP_INVALID') END;
END;

CREATE TRIGGER IF NOT EXISTS membership_source_only_UPDATE BEFORE UPDATE OF child_id,active ON membership WHEN NEW.active=1 BEGIN
    SELECT CASE WHEN EXISTS(
        SELECT 1 FROM work_object child
        WHERE child.id=NEW.child_id AND child.type!='SOURCE'
    ) THEN RAISE(ABORT,'GROUP_INVALID') END;
END;
