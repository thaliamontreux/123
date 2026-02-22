#!/usr/bin/env python3
"""Patch server_menu.py for Textual Log/TextLog compatibility.

Usage:
  python3 scripts/fix_server_menu_textlog.py /path/to/server_menu.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/fix_server_menu_textlog.py /path/to/server_menu.py")
        return 2

    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    original = text

    # 1) Replace TextLog import with Log.
    text = text.replace("Header, Footer, Static, Button, Label, Input, SelectionList, DataTable, TextLog", "Header, Footer, Static, Button, Label, Input, SelectionList, DataTable, Log")

    # 2) Replace TextLog widget creation/query annotations.
    text = text.replace("yield TextLog(id=\"log\", highlight=True)", "yield Log(id=\"log\", highlight=True)")
    text = text.replace("self.query_one(\"#log\", TextLog).write(msg)", "self.query_one(\"#log\", Log).write_line(msg)")

    # 3) Keep CSS selector working for both names.
    text = re.sub(
        r"SelectionList, DataTable, Input, TextLog \{",
        "SelectionList, DataTable, Input, Log {",
        text,
    )

    if text == original:
        print("No changes were needed.")
        return 0

    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
