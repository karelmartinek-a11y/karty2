from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PySide6.QtGui import QColor
from kajovokarty.domain.core import display_money, canonical

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
        self.columns = columns or []

    def replace(self, rows, columns=None):
        self.beginResetModel()
        self.rows = rows
        if columns is not None:
            self.columns = columns
        self.endResetModel()

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
            if key == "resolved" and v is None:
                return "Pomocné / historie"
            if key == "resolved":
                return "Vyřízeno" if v else "Nevyřízeno"
            if key == "type" and v in ("SOURCE", "GROUP"):
                return "Položka" if v == "SOURCE" else "Skupina"
            if key in ("amount", "difference", "pair_difference") and v is not None:
                return display_money(v)
            if key == "kinds":
                return " + ".join(
                    {
                        "CASHBOOK_CARD": "Pokladna",
                        "BANK_CARD": "Terminál",
                        "BOOKING": "Booking",
                    }[k]
                    for k in v
                )
            if isinstance(v, (dict, list)):
                return canonical(v)
            return "" if v is None else str(v)
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
            if value and (date.today() - date.fromisoformat(value[:10])).days > getattr(
                self, "warning_age_days", 30
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
