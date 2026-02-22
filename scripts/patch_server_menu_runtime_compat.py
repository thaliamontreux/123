#!/usr/bin/env python3
"""Patch legacy server_menu.py for modern Textual compatibility.

Fixes:
1) TextLog -> Log import/widget/write API changes.
2) SelectionList.selected compatibility where entries may be raw values (str/int)
   instead of option objects with `.value`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def ensure_helper(text: str) -> str:
    helper = '''

def selection_values(selection_list) -> list:
    """Return selected values across Textual versions.

    Some versions expose SelectionList.selected items as values (str/int),
    others as option objects with `.value`.
    """
    values = []
    for item in selection_list.selected:
        values.append(getattr(item, "value", item))
    return values
'''

    if "def selection_values(selection_list)" in text:
        return text

    marker = "# ----------------------------- Netplan Utility Screens -----------------------------"
    if marker in text:
        return text.replace(marker, helper + "\n" + marker)

    # fallback: append near utility helpers section
    insert_after = "def parse_csv_list(s: str) -> List[str]:"
    idx = text.find(insert_after)
    if idx != -1:
        end = text.find("\n\n", idx)
        if end != -1:
            return text[: end + 2] + helper + text[end + 2 :]

    return text + helper


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_server_menu_runtime_compat.py /path/to/server_menu.py")
        return 2

    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    original = text

    # TextLog -> Log
    text = text.replace(
        "Header, Footer, Static, Button, Label, Input, SelectionList, DataTable, TextLog",
        "Header, Footer, Static, Button, Label, Input, SelectionList, DataTable, Log",
    )
    text = re.sub(r"yield\s+TextLog\(id=[\"']log[\"'],\s*highlight=True\)", "yield Log(id=\"log\", highlight=True)", text)
    text = re.sub(r"self\.query_one\([\"']#log[\"'],\s*TextLog\)\.write\(msg\)", "self.query_one(\"#log\", Log).write_line(msg)", text)
    text = re.sub(r"SelectionList, DataTable, Input, TextLog \{", "SelectionList, DataTable, Input, Log {", text)

    # SelectionList.selected compatibility replacements
    replacements = [
        ("sel = [opt.value for opt in sl.selected]", "sel = selection_values(sl)"),
        ("chosen = [opt.value for opt in sl.selected]", "chosen = selection_values(sl)"),
        ("chosen = [int(opt.value) for opt in sl.selected]", "chosen = [int(v) for v in selection_values(sl)]"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    text = ensure_helper(text)

    if text == original:
        print("No changes were needed.")
        return 0

    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
