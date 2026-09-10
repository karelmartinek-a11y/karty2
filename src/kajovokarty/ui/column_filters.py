"""Visible Excel-style header menus, shared by every table and evidence tree."""

from PySide6.QtCore import Qt, Signal, QRect, QPoint, QTimer, QItemSelectionModel
from PySide6.QtGui import QColor, QPolygon
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QWidget,
    QWidgetAction,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QAbstractItemView,
    QApplication,
)
from shiboken6 import isValid
from kajovokarty.domain.core import search_normalize


class FilterHeader(QHeaderView):
    filterRequested = Signal(int, object)

    def __init__(self, parent):
        super().__init__(Qt.Horizontal, parent)
        self.active = lambda column: False
        self.setSectionsClickable(True)
        self.setSectionsMovable(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.filterRequested.emit(self.logicalIndexAt(pos), pos)
        )

    def paintSection(self, painter, rect, logical):
        # Native styles may modify the painter's clip/transform. Isolate them
        # before drawing our always-visible filter affordance.
        painter.save()
        super().paintSection(painter, rect.adjusted(0, 0, -22, 0), logical)
        painter.restore()
        painter.save()
        active = self.active(logical)
        area = QRect(rect.right() - 21, rect.top() + 2, 20, rect.height() - 4)
        painter.fillRect(area, QColor("#c5def3" if active else "#edf3f8"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#145a91" if active else "#42586b"))
        x, y = area.center().x(), area.center().y()
        painter.drawPolygon(
            QPolygon([QPoint(x - 5, y - 2), QPoint(x + 5, y - 2), QPoint(x, y + 3)])
        )
        if active:
            painter.drawRect(x - 1, y + 3, 3, 4)
        painter.restore()

    def mousePressEvent(self, event):
        col = self.logicalIndexAt(event.position().toPoint())
        if (
            col >= 0
            and event.button() == Qt.LeftButton
            and event.position().x()
            >= self.sectionViewportPosition(col) + self.sectionSize(col) - 24
        ):
            self.filterRequested.emit(col, event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)


class ColumnController:
    def __init__(
        self,
        table,
        model,
        *,
        get_filters=None,
        set_filter=None,
        set_sort=None,
        get_options=None,
    ):
        self.table, self.model = table, model
        self.get_filters = get_filters or (lambda: model.column_filters)
        self.set_filter = set_filter or model.set_column_filter
        self.set_sort = set_sort or model.set_sort
        self.get_options = get_options or (
            lambda field, done: done(model.filter_options(field))
        )
        self.header = FilterHeader(table)
        table.setHorizontalHeader(self.header) if hasattr(
            table, "setHorizontalHeader"
        ) else table.setHeader(self.header)
        self.header.active = (
            lambda col: 0 <= col < len(self.model.columns)
            and self.model.columns[col][0] in self.get_filters()
        )
        self.header.sectionClicked.connect(self.cycle_sort)
        self.header.filterRequested.connect(self.open_menu)
        self.sort = []
        self.menu = None
        self.header.setToolTip(
            "Kliknutí: řazení. Šipka nebo pravé tlačítko: filtr sloupce."
        )
        table.column_controller = self
        if hasattr(model, "modelAboutToBeReset") and not getattr(
            model, "remote", False
        ):
            from kajovokarty.domain.columns import value_token

            selected_ids = set()

            def identity(row):
                return value_token(row.get("id", row))

            def remember():
                selected_ids.clear()
                selected_ids.update(
                    identity(model.rows[i.row()])
                    for i in table.selectionModel().selectedRows()
                )

            def restore():
                for i, row in enumerate(model.rows):
                    if identity(row) in selected_ids:
                        table.selectionModel().select(
                            model.index(i, 0),
                            QItemSelectionModel.Select | QItemSelectionModel.Rows,
                        )

            model.modelAboutToBeReset.connect(remember)
            model.modelReset.connect(restore)

    def refresh(self, sort=None):
        if sort is not None:
            self.sort = list(sort)
        keys = [k for k, _ in self.model.columns]
        shown = bool(self.sort and self.sort[0][0] in keys)
        self.header.setSortIndicatorShown(shown)
        if shown:
            self.header.setSortIndicator(
                keys.index(self.sort[0][0]),
                Qt.DescendingOrder if self.sort[0][1] == "desc" else Qt.AscendingOrder,
            )
        self.header.viewport().update()

    def apply_sort(self, sort):
        self.sort = list(sort)
        self.set_sort(self.sort)
        self.refresh()

    def cycle_sort(self, col):
        field = self.model.columns[col][0]
        previous = next((d for k, d in self.sort if k == field), None)
        # A single click cycles ascending / descending / original order.
        remaining = (
            [(k, d) for k, d in self.sort if k != field]
            if QApplication.keyboardModifiers() & Qt.ShiftModifier
            else []
        )
        if previous != "desc":
            remaining.append((field, "desc" if previous == "asc" else "asc"))
        self.apply_sort(remaining)

    def open_menu(self, col, pos):
        if not 0 <= col < len(self.model.columns):
            return
        field, label = self.model.columns[col]
        menu = QMenu(self.table)
        menu.setObjectName("columnFilterMenu")
        self.menu = menu
        menu.aboutToHide.connect(menu.deleteLater)
        menu.addAction("Řadit vzestupně", lambda: self.apply_sort([(field, "asc")]))
        menu.addAction("Řadit sestupně", lambda: self.apply_sort([(field, "desc")]))
        menu.addAction("Zrušit řazení", lambda: self.apply_sort([]))
        menu.addSeparator()
        clear = menu.addAction("Zrušit filtr sloupce", lambda: self.change(field, None))
        clear.setEnabled(field in self.get_filters())
        menu.addAction("Zrušit všechny filtry tabulky", lambda: self.change(None, None))
        columns = menu.addMenu("Zobrazené sloupce")
        for index, (_, title) in enumerate(self.model.columns):
            action = columns.addAction(title)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(index))
            action.toggled.connect(
                lambda checked, i=index: self.table.setColumnHidden(i, not checked)
            )
        widget = QWidget(menu)
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Filtrovat: " + label))
        search = QLineEdit()
        search.setObjectName("columnFilterSearch")
        search.setPlaceholderText("Hledat hodnotu…")
        layout.addWidget(search)
        buttons = QHBoxLayout()
        select = QPushButton("Vybrat zobrazené")
        none = QPushButton("Odebrat zobrazené")
        buttons.addWidget(select)
        buttons.addWidget(none)
        layout.addLayout(buttons)
        values = QListWidget()
        values.setObjectName("columnFilterValues")
        values.setSelectionMode(QAbstractItemView.NoSelection)
        values.setMinimumSize(340, 230)
        layout.addWidget(values)
        status = QLabel("Načítám hodnoty ze všech výsledků…")
        layout.addWidget(status)
        actions = QHBoxLayout()
        ok = QPushButton("Použít")
        ok.setObjectName("applyColumnFilter")
        ok.setEnabled(False)
        cancel = QPushButton("Zrušit")
        actions.addWidget(ok)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(widget)
        menu.addAction(wa)

        def search_values(text):
            needle = search_normalize(text)
            for i in range(values.count()):
                item = values.item(i)
                item.setHidden(needle not in search_normalize(item.text()))

        search.textChanged.connect(search_values)

        def check_visible(state):
            for i in range(values.count()):
                item = values.item(i)
                if not item.isHidden():
                    item.setCheckState(state)

        select.clicked.connect(lambda: check_visible(Qt.Checked))
        none.clicked.connect(lambda: check_visible(Qt.Unchecked))
        current = self.get_filters().get(field)
        options_seen = set()

        def loaded(options):
            if not isValid(menu) or not menu.isVisible():
                return
            options = list(options)
            options_seen.update(token for _, token in options)
            # Keep a selected but currently absent value explicit, never silently widen a filter.
            options.extend(
                ("(Momentálně mimo výsledek) " + token, token)
                for token in (set(current or []) - options_seen)
            )
            select.setEnabled(False)
            none.setEnabled(False)

            def append_batch(start=0):
                if not isValid(menu) or not menu.isVisible():
                    return
                needle = search_normalize(search.text())
                for title, token in options[start : start + 400]:
                    item = QListWidgetItem(title, values)
                    item.setData(Qt.UserRole, token)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.Checked
                        if current is None or token in current
                        else Qt.Unchecked
                    )
                    item.setHidden(needle not in search_normalize(title))
                end = min(start + 400, len(options))
                status.setText(
                    f"{end} / {len(options)} hodnot · prázdný výběr zobrazí 0 řádků"
                )
                if end < len(options):
                    QTimer.singleShot(0, lambda: append_batch(end))
                else:
                    ok.setEnabled(True)
                    select.setEnabled(True)
                    none.setEnabled(True)

            append_batch()

        def apply():
            selected = [
                values.item(i).data(Qt.UserRole)
                for i in range(values.count())
                if values.item(i).checkState() == Qt.Checked
            ]
            self.change(
                field,
                None if selected and set(selected) == options_seen else selected,
            )
            menu.close()

        ok.clicked.connect(apply)
        cancel.clicked.connect(menu.close)
        menu.popup(self.header.mapToGlobal(pos))
        self.get_options(field, loaded)
        search.setFocus()

    def change(self, field, selected):
        self.set_filter(field, selected)
        self.refresh()
