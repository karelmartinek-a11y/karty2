"""Publish staged files with the destination directory's access permissions.

Moving a file from TemporaryDirectory on Windows also moves its private ACL.
Create the replacement in the destination directory before the atomic rename.
"""
import os
from pathlib import Path
import shutil
from uuid import uuid4


def publish_staged_file(source, target):
    source, target = Path(source), Path(target)
    pending = target.with_name("." + target.name + "." + uuid4().hex + ".tmp")
    try:
        with source.open("rb") as reader, pending.open("xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
