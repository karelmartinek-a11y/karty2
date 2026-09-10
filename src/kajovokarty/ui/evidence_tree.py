"""Column filters preserve matching nodes and their ancestor context in evidence trees."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from kajovokarty.domain.columns import filter_options, matches, sort_value
from kajovokarty.ui.column_filters import ColumnController

RAW_ROLE = Qt.UserRole + 2
ORDER_ROLE = Qt.UserRole + 3


class EvidenceItem(QTreeWidgetItem):
    def __lt__(self, other):
        tree = self.treeWidget()
        if getattr(tree, "original_order", False):
            return self.data(0, ORDER_ROLE) < other.data(0, ORDER_ROLE)
        column = tree.sortColumn()
        a, b = self.data(column, RAW_ROLE), other.data(column, RAW_ROLE)
        if (a is None or a == "") != (b is None or b == ""):
            descending = tree.header().sortIndicatorOrder() == Qt.DescendingOrder
            return (a is None or a == "") if descending else not (a is None or a == "")
        return sort_value(a) < sort_value(b)


class EvidenceTree(QTreeWidget):
    def enable_filters(self):
        self.columns = [
            ("identity", "Jedinečný list / skupina"),
            ("kind", "Zdroj"),
            ("amount", "Původní částka"),
            ("currency", "Měna"),
        ]
        self.column_filters = {}
        self.all_items = []
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            item.setData(0, ORDER_ROLE, len(self.all_items))
            self.all_items.append(item)
            stack.extend(item.child(i) for i in range(item.childCount() - 1, -1, -1))
        ColumnController(self, self)

    def row(self, item):
        return {key: item.data(i, RAW_ROLE) for i, (key, _) in enumerate(self.columns)}

    def filter_options(self, field):
        return filter_options(
            [self.row(item) for item in self.all_items], field, self.column_filters
        )

    def set_column_filter(self, field, selected):
        if field is None:
            self.column_filters.clear()
        elif selected is None:
            self.column_filters.pop(field, None)
        else:
            self.column_filters[field] = list(selected)
        visible = set()
        for item in self.all_items:
            if matches(self.row(item), self.column_filters):
                ancestor = item
                while ancestor is not None:
                    visible.add(id(ancestor))
                    ancestor = ancestor.parent()
        for item in self.all_items:
            item.setHidden(id(item) not in visible)
            if self.column_filters and id(item) in visible:
                item.setExpanded(True)

    def set_sort(self, sort):
        self.original_order = not bool(sort)
        if sort:
            field, direction = sort[0]
            self.sortItems(
                [key for key, _ in self.columns].index(field),
                Qt.DescendingOrder if direction == "desc" else Qt.AscendingOrder,
            )
        else:
            self.sortItems(0, Qt.AscendingOrder)
