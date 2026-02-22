#!/usr/bin/env python3
from __future__ import annotations

import datetime
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Input, Label, DataTable, Log, Select, Checkbox

LOG_FILE = Path("./error.log")


def log(msg: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def run(cmd: List[str]) -> subprocess.CompletedProcess:
    log("RUN: " + shlex.join(cmd))
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if cp.stdout:
        log(cp.stdout)
    return cp


def valid_ip_or_any(value: str) -> bool:
    if value in {"", "any"}:
        return True
    pat = r"^(\d{1,3}\.){3}\d{1,3}(/\d|/[12]\d|/3[0-2])?$"
    if not re.match(pat, value):
        return False
    ip = value.split("/")[0]
    return all(0 <= int(p) <= 255 for p in ip.split("."))


def valid_port_or_any(value: str) -> bool:
    if value in {"", "any"}:
        return True
    if ":" in value:
        a, b = value.split(":", 1)
        return a.isdigit() and b.isdigit() and 1 <= int(a) <= 65535 and 1 <= int(b) <= 65535
    return value.isdigit() and 1 <= int(value) <= 65535


@dataclass
class UfwRule:
    action: str = "allow"  # allow|deny|reject|limit
    direction: str = "in"  # in|out
    proto: str = "tcp"     # tcp|udp|any
    interface: str = ""     # optional
    src_ip: str = "any"
    src_port: str = "any"
    dst_ip: str = "any"
    dst_port: str = "any"
    comment: str = ""
    enabled: bool = True

    def validate(self) -> Optional[str]:
        if self.action not in {"allow", "deny", "reject", "limit"}:
            return "Invalid action"
        if self.direction not in {"in", "out"}:
            return "Invalid direction"
        if self.proto not in {"tcp", "udp", "any"}:
            return "Invalid protocol"
        if not valid_ip_or_any(self.src_ip):
            return "Invalid source IP/CIDR"
        if not valid_ip_or_any(self.dst_ip):
            return "Invalid destination IP/CIDR"
        if not valid_port_or_any(self.src_port):
            return "Invalid source port"
        if not valid_port_or_any(self.dst_port):
            return "Invalid destination port"
        return None

    def to_cmd(self) -> List[str]:
        cmd = ["ufw", self.action]
        if self.direction:
            cmd += [self.direction]
        if self.interface:
            cmd += ["on", self.interface]
        if self.proto != "any":
            cmd += ["proto", self.proto]
        if self.src_ip != "any":
            cmd += ["from", self.src_ip]
        else:
            cmd += ["from", "any"]
        if self.src_port != "any":
            cmd += ["port", self.src_port]
        if self.dst_ip != "any":
            cmd += ["to", self.dst_ip]
        else:
            cmd += ["to", "any"]
        if self.dst_port != "any":
            cmd += ["port", self.dst_port]
        if self.comment.strip():
            cmd += ["comment", self.comment.strip()]
        return cmd


class SubScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    def top(self, title: str) -> Container:
        return Container(
            Horizontal(Button("← Back", id="back_top", variant="warning"), Label(f"[b]{title}[/b]")),
            id="topbar",
        )

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back_top":
            self.app.pop_screen()


class UfwRuleEditor(SubScreen):
    def __init__(self, parent: "UfwAdvancedScreen", idx: Optional[int]):
        super().__init__()
        self.parent_screen = parent
        self.idx = idx
        self.rule = parent.rules[idx] if idx is not None else UfwRule()

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.top("UFW Rule Editor")
        yield Container(
            Label("Action"), Select([(x, x) for x in ["allow", "deny", "reject", "limit"]], value=self.rule.action, id="action"),
            Label("Direction"), Select([(x, x) for x in ["in", "out"]], value=self.rule.direction, id="dir"),
            Label("Protocol"), Select([(x, x) for x in ["tcp", "udp", "any"]], value=self.rule.proto, id="proto"),
            Label("Interface (optional)"), Input(value=self.rule.interface, id="iface"),
            Label("Source IP/CIDR (or any)"), Input(value=self.rule.src_ip, id="src_ip"),
            Label("Source Port (or any)"), Input(value=self.rule.src_port, id="src_port"),
            Label("Destination IP/CIDR (or any)"), Input(value=self.rule.dst_ip, id="dst_ip"),
            Label("Destination Port (or any)"), Input(value=self.rule.dst_port, id="dst_port"),
            Label("Description/Comment"), Input(value=self.rule.comment, id="comment"),
            Checkbox("Enabled", value=self.rule.enabled, id="enabled"),
            Horizontal(Button("Save", id="save", variant="primary"), Button("Cancel", id="cancel")),
            id="pane",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        if event.button.id == "cancel":
            self.app.pop_screen()
            return
        if event.button.id == "save":
            new = UfwRule(
                action=str(self.query_one("#action", Select).value),
                direction=str(self.query_one("#dir", Select).value),
                proto=str(self.query_one("#proto", Select).value),
                interface=self.query_one("#iface", Input).value.strip(),
                src_ip=self.query_one("#src_ip", Input).value.strip() or "any",
                src_port=self.query_one("#src_port", Input).value.strip() or "any",
                dst_ip=self.query_one("#dst_ip", Input).value.strip() or "any",
                dst_port=self.query_one("#dst_port", Input).value.strip() or "any",
                comment=self.query_one("#comment", Input).value.strip(),
                enabled=self.query_one("#enabled", Checkbox).value,
            )
            err = new.validate()
            if err:
                self.app.notify(err, severity="error")
                return
            if self.idx is None:
                self.parent_screen.rules.append(new)
            else:
                self.parent_screen.rules[self.idx] = new
            self.parent_screen.refresh_table()
            self.app.pop_screen()


class UfwAdvancedScreen(SubScreen):
    def __init__(self, app_ref: "UbuntuAdminApp"):
        super().__init__()
        self.app_ref = app_ref
        self.rules: List[UfwRule] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.top("Extensive UFW Firewall Configuration")
        table = DataTable(id="rules")
        table.add_columns("#", "En", "Action", "Dir", "Proto", "Iface", "Src", "SPort", "Dst", "DPort", "Comment")
        yield Container(
            Static("┌─ Rule List (editable) ─────────────────────────────┐\n│ Add / Edit / Test / Apply rules with full fields. │\n└────────────────────────────────────────────────────┘"),
            table,
            Horizontal(Button("Add", id="add", variant="primary"), Button("Edit", id="edit"), Button("Delete", id="del"), Button("Test Selected", id="test"), Button("Apply Enabled", id="apply"), Button("UFW Status", id="status")),
            id="pane",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_table()

    def selected_idx(self) -> Optional[int]:
        t = self.query_one("#rules", DataTable)
        if t.cursor_row is None:
            return None
        row = t.get_row_at(t.cursor_row)
        return int(str(row[0])) if row else None

    def refresh_table(self) -> None:
        t = self.query_one("#rules", DataTable)
        t.clear()
        for i, r in enumerate(self.rules):
            t.add_row(str(i), "Y" if r.enabled else "N", r.action, r.direction, r.proto, r.interface or "-", r.src_ip, r.src_port, r.dst_ip, r.dst_port, r.comment or "-")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        bid = event.button.id
        if bid == "add":
            self.app.push_screen(UfwRuleEditor(self, None))
        elif bid == "edit":
            idx = self.selected_idx()
            if idx is None:
                self.app.notify("Select a rule", severity="warning")
                return
            self.app.push_screen(UfwRuleEditor(self, idx))
        elif bid == "del":
            idx = self.selected_idx()
            if idx is None:
                self.app.notify("Select a rule", severity="warning")
                return
            self.rules.pop(idx)
            self.refresh_table()
        elif bid == "test":
            idx = self.selected_idx()
            if idx is None:
                self.app.notify("Select a rule", severity="warning")
                return
            cmd = ["ufw", "--dry-run"] + self.rules[idx].to_cmd()[1:]
            out = run(cmd).stdout or ""
            self.app_ref.log_ui(out[-3000:])
        elif bid == "apply":
            for r in self.rules:
                if r.enabled:
                    run(r.to_cmd())
            self.app.notify("Applied enabled rules")
        elif bid == "status":
            out = run(["ufw", "status", "verbose"]).stdout or ""
            self.app_ref.log_ui(out[-3000:])


class GitAdvancedScreen(SubScreen):
    def __init__(self, app_ref: "UbuntuAdminApp"):
        super().__init__()
        self.app_ref = app_ref

    def gget(self, key: str, default: str = "") -> str:
        cp = run(["git", "config", "--global", key])
        return (cp.stdout or "").strip() or default

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.top("Extensive Git Configuration")
        yield Container(
            Label("User Name"), Input(value=self.gget("user.name"), id="name", classes="field"),
            Label("User Email"), Input(value=self.gget("user.email"), id="email", classes="field"),
            Label("Default Branch"), Input(value=self.gget("init.defaultBranch", "main"), id="branch", classes="field"),
            Label("Core Editor"), Input(value=self.gget("core.editor", "joe"), id="editor", classes="field"),
            Label("Pull Rebase (true/false)"), Input(value=self.gget("pull.rebase", "false"), id="rebase", classes="field"),
            Label("Push Default"), Input(value=self.gget("push.default", "simple"), id="pushdefault", classes="field"),
            Label("Default Remote"), Input(value=self.gget("clone.defaultRemoteName", "origin"), id="remote", classes="field"),
            Label("Credential Helper"), Input(value=self.gget("credential.helper", "cache"), id="cred", classes="field"),
            Horizontal(Button("Save", id="save", variant="primary"), Button("Show Current", id="show")),
            id="pane",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        if event.button.id == "save":
            mapping = {
                "user.name": self.query_one("#name", Input).value.strip(),
                "user.email": self.query_one("#email", Input).value.strip(),
                "init.defaultBranch": self.query_one("#branch", Input).value.strip() or "main",
                "core.editor": self.query_one("#editor", Input).value.strip() or "joe",
                "pull.rebase": self.query_one("#rebase", Input).value.strip() or "false",
                "push.default": self.query_one("#pushdefault", Input).value.strip() or "simple",
                "clone.defaultRemoteName": self.query_one("#remote", Input).value.strip() or "origin",
                "credential.helper": self.query_one("#cred", Input).value.strip() or "cache",
            }
            for k, v in mapping.items():
                run(["git", "config", "--global", k, v])
            self.app.notify("Git settings saved")
        elif event.button.id == "show":
            out = run(["git", "config", "--global", "--list"]).stdout or ""
            self.app_ref.log_ui(out[-4000:])


class WebConfigScreen(SubScreen):
    def __init__(self, app_ref: "UbuntuAdminApp"):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.top("Nginx / Apache Website & Proxy Helper")
        yield Container(
            Label("Engine"), Select([("nginx", "nginx"), ("apache", "apache")], value="nginx", id="engine"),
            Label("Site Name"), Input(placeholder="example.local", id="site", classes="field"),
            Label("Listen Port"), Input(value="80", id="listen", classes="field"),
            Label("Server Name(s)"), Input(placeholder="example.local www.example.local", id="server_names", classes="field"),
            Label("Proxy Target (socket or ip:port)"), Input(placeholder="127.0.0.1:3000 or unix:/run/app.sock", id="target", classes="field"),
            Horizontal(Button("Create/Update", id="create", variant="primary"), Button("Test Config", id="test"), Button("Apply+Restart", id="apply")),
            id="pane",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        engine = str(self.query_one("#engine", Select).value)
        site = self.query_one("#site", Input).value.strip()
        listen = self.query_one("#listen", Input).value.strip() or "80"
        names = self.query_one("#server_names", Input).value.strip() or site
        target = self.query_one("#target", Input).value.strip()
        if event.button.id == "create":
            if not site or not target:
                self.app.notify("Site and target required", severity="error")
                return
            if engine == "nginx":
                conf = f"""server {{\n  listen {listen};\n  server_name {names};\n  location / {{\n    proxy_pass http://{target};\n    proxy_set_header Host $host;\n    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n  }}\n}}\n"""
                p = Path(f"/etc/nginx/sites-available/{site}.conf")
                p.write_text(conf, encoding="utf-8")
                en = Path(f"/etc/nginx/sites-enabled/{site}.conf")
                if not en.exists():
                    en.symlink_to(p)
            else:
                conf = f"""<VirtualHost *:{listen}>\n ServerName {site}\n ServerAlias {names}\n ProxyPreserveHost On\n ProxyPass / http://{target}/\n ProxyPassReverse / http://{target}/\n</VirtualHost>\n"""
                p = Path(f"/etc/apache2/sites-available/{site}.conf")
                p.write_text(conf, encoding="utf-8")
                run(["a2enmod", "proxy", "proxy_http"])
                run(["a2ensite", f"{site}.conf"])
            self.app.notify("Configuration written")
        elif event.button.id == "test":
            out = run(["nginx", "-t"] if engine == "nginx" else ["apachectl", "configtest"]).stdout or ""
            self.app_ref.log_ui(out[-3000:])
        elif event.button.id == "apply":
            run(["systemctl", "restart", "nginx" if engine == "nginx" else "apache2"])
            self.app.notify("Service restarted")


class Fail2banConfigScreen(SubScreen):
    def __init__(self, app_ref: "UbuntuAdminApp"):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.top("Fail2Ban Configuration Utility")
        yield Container(
            Label("Bantime"), Input(value="1h", id="bantime", classes="field"),
            Label("Findtime"), Input(value="10m", id="findtime", classes="field"),
            Label("Maxretry"), Input(value="5", id="maxretry", classes="field"),
            Label("Jails enabled (csv, e.g. sshd,nginx-http-auth,apache-auth)"), Input(value="sshd", id="jails", classes="field"),
            Horizontal(Button("Write jail.local", id="write", variant="primary"), Button("Restart", id="restart"), Button("Diagnostics", id="diag")),
            id="pane",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        if event.button.id == "write":
            bantime = self.query_one("#bantime", Input).value.strip()
            findtime = self.query_one("#findtime", Input).value.strip()
            maxretry = self.query_one("#maxretry", Input).value.strip()
            jails = [x.strip() for x in self.query_one("#jails", Input).value.split(",") if x.strip()]
            lines = ["[DEFAULT]", f"bantime = {bantime}", f"findtime = {findtime}", f"maxretry = {maxretry}", ""]
            for j in jails:
                lines += [f"[{j}]", "enabled = true", "",]
            Path("/etc/fail2ban/jail.local").write_text("\n".join(lines), encoding="utf-8")
            self.app.notify("/etc/fail2ban/jail.local written")
        elif event.button.id == "restart":
            run(["systemctl", "restart", "fail2ban"])
            self.app.notify("fail2ban restarted")
        elif event.button.id == "diag":
            out = run(["fail2ban-client", "status"]).stdout or ""
            self.app_ref.log_ui(out[-3000:])


class JoeConfigScreen(SubScreen):
    def __init__(self, app_ref: "UbuntuAdminApp"):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.top("JOE Global Options Utility")
        yield Container(
            Static("Frequently toggled options are shown first."),
            Checkbox("Autoindent", id="autoindent", value=True),
            Checkbox("Wordwrap", id="wordwrap", value=True),
            Checkbox("Syntax Highlight", id="syntax", value=True),
            Checkbox("Status Bar", id="status", value=True),
            Checkbox("Show Line Numbers", id="linenos", value=True),
            Horizontal(Button("Apply", id="apply", variant="primary"), Button("Diagnostics", id="diag")),
            id="pane",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        if event.button.id == "apply":
            options = {
                "autoindent": self.query_one("#autoindent", Checkbox).value,
                "wordwrap": self.query_one("#wordwrap", Checkbox).value,
                "syntax": self.query_one("#syntax", Checkbox).value,
                "status": self.query_one("#status", Checkbox).value,
                "linenos": self.query_one("#linenos", Checkbox).value,
            }
            cfg = Path("/etc/joe/joerc.d/server-menu.rc")
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text("\n".join([f"set {k}={'on' if v else 'off'}" for k, v in options.items()]) + "\n", encoding="utf-8")
            self.app.notify(f"Wrote {cfg}")
        elif event.button.id == "diag":
            self.app_ref.log_ui("JOE config snippets:\n" + "\n".join(str(p) for p in Path("/etc/joe").glob("**/*.rc")))


class UbuntuAdminApp(App):
    TITLE = "Ubuntu Administration Assistant"
    CSS = """
    Screen { background: #0b3d91; color: white; }
    #root { height: 100%; }
    #left { width: 36; border: tall $panel; }
    #right { border: tall $panel; }
    #pane { padding: 1; overflow-y: auto; height: 1fr; }
    Input.field { background: #ffe8a3; color: black; border: round #222222; }
    Select, Input, DataTable, Log { background: #ffffff; color: #000000; }
    #topbar { background: #123; padding: 0 1; }
    """
    BINDINGS = [Binding("q", "quit", "Quit"), Binding("up", "scroll_up", "Scroll Up"), Binding("down", "scroll_down", "Scroll Down")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="root"):
            with Vertical(id="left"):
                yield Static("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃ Ubuntu Administration Assistant    ┃\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
                yield Button("Extensive Git Configuration", id="git", variant="primary")
                yield Button("Extensive UFW Firewall", id="ufw", variant="primary")
                yield Button("Nginx/Apache Website & Proxy Helper", id="web")
                yield Button("Fail2Ban Utility", id="f2b")
                yield Button("JOE Utility", id="joe")
                yield Button("Service Diagnostics", id="diag")
            with Vertical(id="right"):
                yield Static("┌─ Activity / Diagnostics (scrollable) ──────────────────────────┐\n└──────────────────────────────────────────────────────────────────┘")
                yield Log(id="activity", highlight=True, auto_scroll=True)
        yield Footer()

    def log_ui(self, msg: str) -> None:
        self.query_one("#activity", Log).write_line(msg)
        log(msg)

    def action_scroll_up(self) -> None:
        self.query_one("#activity", Log).scroll_home(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one("#activity", Log).scroll_end(animate=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "git":
            self.push_screen(GitAdvancedScreen(self))
        elif bid == "ufw":
            self.push_screen(UfwAdvancedScreen(self))
        elif bid == "web":
            self.push_screen(WebConfigScreen(self))
        elif bid == "f2b":
            self.push_screen(Fail2banConfigScreen(self))
        elif bid == "joe":
            self.push_screen(JoeConfigScreen(self))
        elif bid == "diag":
            out = run(["bash", "-lc", "systemctl --failed --no-pager; echo; ufw status verbose; echo; git --version"]).stdout or ""
            self.log_ui(out[-5000:])


def main() -> None:
    if os.geteuid() != 0:
        print("Run as root: sudo python3 server_menu.py")
        raise SystemExit(1)
    if shutil.which("textual"):
        pass
    UbuntuAdminApp().run()


if __name__ == "__main__":
    main()
