# Fix for `ImportError: cannot import name 'TextLog' from textual.widgets`

Newer Textual releases use `Log` instead of `TextLog`.

## Manual changes in `server_menu.py`

1. Change import:

```python
from textual.widgets import (
    Header, Footer, Static, Button, Label, Input, SelectionList, DataTable, Log
)
```

2. Change widget creation:

```python
yield Log(id="log", highlight=True)
```

3. Change logging write call:

```python
self.query_one("#log", Log).write_line(msg)
```

4. Optional CSS selector update:

```css
SelectionList, DataTable, Input, Log {
    background: white; color: black; border: round white;
}
```

## Automatic patcher

Use the included patch script:

```bash
python3 scripts/fix_server_menu_textlog.py /home/thalia/server_menu.py
```

Then run your app again:

```bash
sudo python3 /home/thalia/server_menu.py
```
