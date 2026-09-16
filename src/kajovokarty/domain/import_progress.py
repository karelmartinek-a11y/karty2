"""Import progress stays compatible with callers accepting text messages."""
class ImportProgress(str):
    def __new__(cls, stage, current=0, total=None, **fields):
        obj = str.__new__(cls, stage)
        obj.snapshot = dict(stage=stage, current=current, total=total, **fields)
        return obj


def notify(callback, stage, current=0, total=None):
    if callback:
        callback(ImportProgress(stage, current, total))
