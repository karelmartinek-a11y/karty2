from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PySide6.QtGui import QColor, QFont
from datetime import date
from PySide6.QtWidgets import QHeaderView
from kajovokarty.domain.columns import display_value, filter_rows, filter_options

WORK_COLUMNS = [
    ("resolved", "Stav"),
    ("type", "Objekt"),
    ("kinds", "Zdroje"),
    ("date", "Datum"),
    ("primary_identifier", "Identifikátor"),
    ("description", "Popis / klient"),
    ("leaf_count", "Počet plateb"),
    ("amount", "Částka"),
    ("currency", "Měna"),
    ("difference", "Rozdíl"),
    ("reason", "Důvod"),
    ("note", "Poznámka"),
]

HIDDEN_PAYMENT_COLUMNS = frozenset({"reason", "note", "difference", "resolved", "type", "pair_difference", "leaf_count"})
COMPACT_WIDTHS = {'kinds': 56, 'date': 94, 'amount': 100, 'currency': 52,
                  'primary_identifier': 116, 'description': 120}


def compact_payment_columns(table):
    table.horizontalHeader().setStyleSheet('QHeaderView::section { padding:4px 2px; }')
    metrics = table.fontMetrics()
    header_metrics = table.horizontalHeader().fontMetrics()
    widths = {**COMPACT_WIDTHS,
              'kinds': max(56, metrics.horizontalAdvance('Zdroj') + 26),
              'currency': max(52, metrics.horizontalAdvance('Měna') + 26),
              'date': max(94, metrics.horizontalAdvance('23.05.2026') + 26),
              'amount': max(100, metrics.horizontalAdvance('1 234 567,89') + 20),
              'primary_identifier': max(116, metrics.horizontalAdvance('FA20265465') + 26)}
    for i, (key, _) in enumerate(table.model().columns):
        if key in widths:
            label = table.model().columns[i][1]
            table.setColumnWidth(i, max(widths[key], header_metrics.horizontalAdvance(label) + 30))
        if key == 'description':
            table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)


def payment_columns(booking_only=False):
    return [(key, "Booking.com ID" if booking_only and key == "primary_identifier" else label)
            for key, label in WORK_COLUMNS]


def hide_payment_columns(table, columns):
    for index, (key, _) in enumerate(columns):
        if key in HIDDEN_PAYMENT_COLUMNS:
            table.setColumnHidden(index, True)


class TableModel(QAbstractTableModel):
    def __init__(self, rows=None, columns=None):
        super().__init__()
        self.rows = rows or []
        self.source_rows = list(self.rows)
        self.column_filters = {}
        self.sort_order = []
        self.remote = False
        self.columns = columns or []
        self.bold_ids = set()

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

    def set_bold_ids(self, ids):
        self.bold_ids = set(ids or ())
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.FontRole],
            )

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
        if not index.isValid() or index.row() >= len(self.rows) or index.column() >= len(self.columns):
            return None
        key = self.columns[index.column()][0]
        v = self.rows[index.row()].get(key)
        if key == "primary_identifier" and self.columns[index.column()][1] == "Booking.com ID" and self.rows[index.row()].get("type") == "GROUP":
            v = None
        if role == Qt.DisplayRole:
            if key == 'kinds' and isinstance(v, (list, tuple)):
                names = {'BANK_CARD': 'T', 'CASHBOOK_CARD': 'P', 'BOOKING': 'B'}
                return '+'.join(names.get(k, k) for k in sorted(v))
            if key in ('date', 'date_end') and v:
                try:
                    return date.fromisoformat(str(v)).strftime('%d.%m.%Y')
                except ValueError:
                    pass
            return display_value(key, v)
        if role in (Qt.ToolTipRole, Qt.AccessibleTextRole):
            return display_value(key, v)
        if role == Qt.TextAlignmentRole and key in (
            "amount",
            "difference",
            "leaf_count",
        ):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and not getattr(self, "high_contrast", False):
            return QColor("#000000" if self.rows[index.row()].get("resolved") else "#a13235")
        if role == Qt.FontRole and self.rows[index.row()].get("id") in self.bold_ids:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.UserRole:
            return v

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if section < 0:
            return None
        if orientation == Qt.Horizontal:
            return self.columns[section][1] if section < len(self.columns) else None
        if orientation == Qt.Vertical:
            return str(section + 1) if section < len(self.rows) else None
        return None
