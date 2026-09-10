"""Non-modal result of an explicitly requested automatic matching run."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QDialogButtonBox,
)
from kajovokarty.domain.columns import REASON_NAMES


def result_text(result):
    lines = [
        f"Zdrojových položek ve vstupním snímku: {result['analyzed_leaves']}",
        f"Nově vyřízeno položek: {result['newly_resolved_leaves']}",
        f"Vytvořeno skupin: {result['created_groups']} · Počet kol: {result['rounds']}",
        "Běh dosáhl ustálení podle platných pravidel."
        if result["reached_fixed_point"]
        else "Běh byl přerušen před ustálením. Dokončené skupiny zůstaly zachovány.",
        f"Oblasti s limitem hledání: {result['limited_components']}",
        f"Pokladní položky bez ověřeného pomocného řetězce: {result['invalid_helper_leaves']}",
    ]
    for currency, counts in result["by_currency"].items():
        lines += [
            "",
            currency,
            f"Vstup {counts['analyzed_leaves']} položek; nově vyřízeno {counts['newly_resolved_leaves']} položek v {counts['created_groups']} skupinách.",
            f"Zbývá {counts['remaining_unresolved_roots']} nevyřízených řádků přehledu, z toho {counts['remaining_free_leaves']} samostatných položek.",
        ]
        lines += [
            f"• {REASON_NAMES.get(reason, reason)}: {count}"
            for reason, count in sorted(counts["reasons"].items())
        ]
    labels = {
        "A": "Storno terminálu",
        "B": "Booking přes doklad",
        "C_STRONG": "Banka se shodným VS",
        "C_WEAK": "Banka s ověřeným kontextem",
        "D": "Booking započtení",
    }
    if result["groups_by_rule"]:
        lines += ["", "Vytvořené skupiny podle pravidla:"]
        lines += [
            f"• {labels[rule]}: {count}"
            for rule, count in sorted(result["groups_by_rule"].items())
        ]
    lines += [
        "",
        "Nejednoznačné shody se automaticky nepotvrzují. Limit či neověřená pomocná data mohou bránit dalším shodám.",
        "Ctrl+Z vrátí poslední vytvořenou skupinu. Další automatické párování spustíte opět tlačítkem.",
        "Tento výsledek zůstává v Nastavení → operace → detail běhu.",
        "Běh: " + result["operation_id"],
    ]
    return "\n".join(lines)


def show_result(parent, result, error=None):
    dialog = QDialog(parent)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setObjectName("automaticMatchingResult")
    dialog.setWindowTitle("Výsledek automatického párování")
    dialog.resize(820, 650)
    layout = QVBoxLayout(dialog)
    heading = QLabel(error.message if error else "Automatické párování dokončeno")
    heading.setWordWrap(True)
    layout.addWidget(heading)
    box = QPlainTextEdit()
    box.setReadOnly(True)
    box.setPlainText(result_text(result))
    layout.addWidget(box)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.button(QDialogButtonBox.Close).setText("Zavřít")
    buttons.rejected.connect(dialog.close)
    layout.addWidget(buttons)
    dialog.show()
    return dialog
