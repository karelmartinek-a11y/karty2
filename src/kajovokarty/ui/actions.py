from dataclasses import dataclass
from typing import Callable
from PySide6.QtGui import QAction, QKeySequence


@dataclass
class ActionSpec:
    id: str
    label: str
    shortcut: str
    allowed_types: tuple
    predicate: Callable
    disabled_reason: str
    handler: Callable


class ActionRegistry:
    def __init__(self, parent):
        self.parent = parent
        self.specs = {}
        self.actions = {}

    def register(self, spec):
        self.specs[spec.id] = spec
        a = QAction(spec.label, self.parent)
        a.setObjectName(spec.id)
        a.setToolTip(spec.label)
        if spec.shortcut:
            a.setShortcut(QKeySequence(spec.shortcut))
        a.triggered.connect(lambda checked=False: self.invoke(spec.id))
        self.actions[spec.id] = a
        self.parent.addAction(a)
        return a

    def invoke(self, id, *args, **kwargs):
        s = self.specs[id]
        if s.predicate():
            s.handler(*args, **kwargs)

    def refresh(self):
        from shiboken6 import isValid

        if not isValid(self.parent) or (
            hasattr(self.parent, "table") and not isValid(self.parent.table)
        ):
            return
        for id, s in self.specs.items():
            self.actions[id].setEnabled(s.predicate())
            self.actions[id].setToolTip(s.label if s.predicate() else s.disabled_reason)

    def button(self, label, handler):
        from PySide6.QtWidgets import QPushButton

        # Reuse the same action object for alternative entries of registered commands.
        key = next(
            (key for key, spec in self.specs.items() if spec.handler == handler), None
        )
        if key is None:
            key = (
                "button:"
                + getattr(handler, "__name__", "action")
                + ":"
                + str(len(self.specs))
            )
            read_only = label.startswith(
                (
                    "Zrušit",
                    "Zavřít",
                    "Předchozí",
                    "Další",
                    "Kopírovat",
                    "Nápověda",
                    "Obnovit pohled",
                    "Původní",
                    "Historie",
                    "Detail",
                )
            )
            self.register(
                ActionSpec(
                    key,
                    label,
                    "",
                    (),
                    lambda: read_only or not self.parent.busy,
                    "Probíhá jiná operace.",
                    handler,
                )
            )
        action = self.actions[key]
        button = QPushButton(label)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(action.trigger)

        def refresh():
            from shiboken6 import isValid

            if isValid(button):
                button.setEnabled(action.isEnabled())
                button.setToolTip(action.toolTip())

        action.changed.connect(refresh)
        refresh()
        return button
