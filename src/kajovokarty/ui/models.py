from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PySide6.QtGui import QColor
from kajovokarty.domain.columns import display_value, filter_rows, filter_options

WORK_COLUMNS = [
    ("resolved", "Stav"),
    ("type", "Objekt"),
    ("kinds", "Zdroje"),
    ("date", "Datum"),
    ("primary_identifier", "Identifikátor"),
    ("description", "Popis / klient"),
    ("leaf_count", "Počet listů"),
    ("amount", "Částka"),
    ("currency", "Měna"),
    ("difference", "Rozdíl"),
    ("reason", "Důvod"),
    ("note", "Poznámka"),
]


class TableModel(QAbstractTableModel):
    def __init__(self, rows=None, columns=None):
        super().__init__()
        self.rows = rows or []
        self.source_rows = list(self.rows)
        self.column_filters = {}
        self.sort_order = []
        self.remote = False
        self.columns = columns or []

    def replace(self, rows, columns=None):
        self.beginResetModel()
        self.source_rows = list(rows)
        self.rows = (
            list(rows)
            if self.remote
            else filter_rows(rows, self.column_filters, self.sort_order)
        )
        if columns is not None:
            self.columns = columns
        self.endResetModel()

    def set_column_filter(self, field, selected):
        if field is None:
            self.column_filters.clear()
        elif selected is None:
            self.column_filters.pop(field, None)
        else:
            self.column_filters[field] = list(selected)
        self.replace(self.source_rows)

    def set_sort(self, sort):
        self.sort_order = list(sort)
        self.replace(self.source_rows)

    def filter_options(self, field):
        return filter_options(self.source_rows, field, self.column_filters)

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.rows[index.row()].get("type") in (
            "SOURCE",
            "GROUP",
        ):
            return flags | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        return flags

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        key = self.columns[index.column()][0]
        v = self.rows[index.row()].get(key)
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return display_value(key, v)
        if role == Qt.TextAlignmentRole and key in (
            "amount",
            "difference",
            "leaf_count",
        ):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if (
            role == Qt.ForegroundRole
            and key == "difference"
            and v is not None
            and not getattr(self, "high_contrast", False)
        ):
            return QColor("#a13235" if v > 0 else "#145c86" if v < 0 else "#176747")
        if role == Qt.BackgroundRole and not self.rows[index.row()].get("resolved"):
            from datetime import date

            value = self.rows[index.row()].get("date")
            if (
                isinstance(value, str)
                and len(value) >= 10
                and value[:4].isdigit()
                and (date.today() - date.fromisoformat(value[:10])).days
                > getattr(self, "warning_age_days", 30)
            ):
                return QColor("#fff7e6")
        if role == Qt.UserRole:
            return v

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return (
                self.columns[section][1]
                if orientation == Qt.Horizontal
                else str(section + 1)
            )
