#!/usr/bin/env python3
"""Minimal Server Menu for Ubuntu 24.04 minimal servers.

A terminal-native administration suite built with Textual.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import pwd
import re
import shutil
import subprocess
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from textual import on
except ImportError:
    try:
        from textual.on import on
    except ImportError:
        from textual._on import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Pretty,
    Select,
    Static,
    TextArea,
)

PUBLIC_DNS = [
    "8.8.8.8",
    "8.8.4.4",
    "1.1.1.1",
    "1.0.0.1",
    "9.9.9.9",
    "149.112.112.112",
    "208.67.222.222",
    "208.67.220.220",
]

VLAN_PRESETS: dict[int, dict[str, Any]] = {
    2: {"prefix": "192.168.2", "routers": [{"gateway": "192.168.2.1", "public": "96.45.17.170"}]},
    3: {"prefix": "192.168.3", "routers": [{"gateway": "192.168.3.1", "public": "96.45.17.170"}]},
    5: {"prefix": "192.168.5", "routers": [{"gateway": "192.168.5.1", "public": "96.45.17.170"}]},
    10: {"prefix": "192.168.1", "routers": [{"gateway": "192.168.1.1", "public": "96.45.17.170"}]},
    99: {"prefix": "192.168.99", "routers": [{"gateway": "192.168.99.1", "public": "96.45.17.170"}]},
    250: {
        "prefix": "192.168.250",
        "routers": [
            {"gateway": "192.168.250.250", "public": "96.45.17.170"},
            {"gateway": "192.168.250.231", "public": "96.45.17.171"},
            {"gateway": "192.168.250.232", "public": "96.45.17.172"},
            {"gateway": "192.168.250.233", "public": "96.45.17.173"},
            {"gateway": "192.168.250.234", "public": "96.45.17.174"},
            {"gateway": "192.168.250.235", "public": "96.45.17.168"},
            {"gateway": "192.168.250.236", "public": "96.45.17.169"},
        ],
    },
    251: {"prefix": "192.168.254", "routers": [{"gateway": "192.168.254.1", "public": "96.45.17.170"}]},
    300: {"prefix": "10.0.1", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
    301: {"prefix": "10.0.2", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
    302: {"prefix": "10.0.3", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
    303: {"prefix": "10.0.4", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
    304: {"prefix": "10.0.5", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
    305: {"prefix": "10.0.6", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
    306: {"prefix": "10.0.7", "routers": [{"gateway": "10.0.1.1", "public": "96.45.17.170"}]},
}

PACKAGE_GROUPS = {
    "Web": ["nginx", "apache2", "php-fpm", "php-cli", "php-curl", "php-xml", "php-mbstring"],
    "Languages": ["python3", "python3-pip", "python3-venv", "perl"],
    "Development": ["build-essential", "clang", "cmake", "gdb", "pkg-config", "libssl-dev", "libffi-dev"],
    "Editors": ["joe", "nano", "vim"],
    "Networking": ["curl", "wget", "dnsutils", "iproute2", "rsync"],
    "Security": ["ufw", "fail2ban", "unattended-upgrades"],
    "Monitoring": ["htop", "iotop", "iftop", "nload"],
}

PROFILES = {
    "Web Server Profile": ["Web", "Security", "Monitoring"],
    "Dev Profile": ["Languages", "Development", "Editors", "Networking"],
    "Ops Profile": ["Networking", "Security", "Monitoring", "Editors"],
    "Hardened Server Profile": ["Security", "Monitoring", "Networking"],
}

COMMON_SERVICES = ["ssh", "nginx", "apache2", "php8.3-fpm", "fail2ban", "ufw"]


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("server_menu")
    logger.setLevel(logging.INFO)
    log_path = Path("./error.log")
    if not os.access(log_path.parent, os.W_OK):
        log_path = Path("/var/log/server-menu.error.log")
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    user = pwd.getpwuid(os.getuid()).pw_name
    logger.info("Startup uid=%s user=%s cwd=%s", os.getuid(), user, os.getcwd())
    return logger


@dataclass
class CommandResult:
    ok: bool
    code: int
    command: str
    output: str


class SystemOps:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def run(self, command: list[str], check: bool = False) -> CommandResult:
        try:
            self.logger.info("EXEC: %s", " ".join(command))
            proc = subprocess.run(command, capture_output=True, text=True, check=check)
            output = (proc.stdout or "") + (proc.stderr or "")
            self.logger.info("RC=%s OUTPUT=%s", proc.returncode, output.strip())
            return CommandResult(proc.returncode == 0, proc.returncode, " ".join(command), output.strip())
        except Exception:
            self.logger.exception("Command failed: %s", command)
            return CommandResult(False, 1, " ".join(command), traceback.format_exc())


class Validator:
    HOST_RE = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$")

    @staticmethod
    def hostname(value: str) -> bool:
        return all(Validator.HOST_RE.match(part) for part in value.split(".")) and len(value) <= 253

    @staticmethod
    def ipv4(value: str) -> bool:
        try:
            ipaddress.IPv4Address(value)
            return True
        except Exception:
            return False

    @staticmethod
    def cidr(value: str) -> bool:
        try:
            ipaddress.ip_interface(value)
            return True
        except Exception:
            return False

    @staticmethod
    def vlan_id(value: int) -> bool:
        return 1 <= value <= 4094

    @staticmethod
    def mtu(value: int) -> bool:
        return 576 <= value <= 9000


@dataclass
class IPv4Config:
    mode: str = "dhcp"  # dhcp|static|disabled
    address: str = ""
    gateway: str = ""


@dataclass
class IPv6Config:
    mode: str = "disabled"  # dhcp|static|disabled
    address: str = ""
    gateway: str = ""


@dataclass
class VLANConfig:
    vlan_id: int
    parent: str
    use_preset: bool = True
    prefix: str = ""
    host_octet: int = 10
    ipv4: IPv4Config = field(default_factory=IPv4Config)
    ipv6: IPv6Config = field(default_factory=IPv6Config)
    dns: list[str] = field(default_factory=lambda: PUBLIC_DNS.copy())
    search: list[str] = field(default_factory=list)
    mtu: int | None = None
    optional: bool = True
    router_index: int = 0

    def build_ipv4_address(self) -> str:
        if self.use_preset and self.prefix:
            return f"{self.prefix}.{self.host_octet}/24"
        return self.ipv4.address


class NetplanManager:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.path = Path("/etc/netplan/99-server-menu.yaml")
        self.backup_dir = Path("/etc/netplan/.server-menu-backups")

    def render(self, interfaces: dict[str, dict[str, Any]], vlans: list[VLANConfig]) -> str:
        lines = ["network:", "  version: 2", "  renderer: networkd", "  ethernets:"]
        for iface, cfg in interfaces.items():
            lines.extend([
                f"    {iface}:",
                f"      dhcp4: {'true' if cfg.get('dhcp4', True) else 'false'}",
                f"      dhcp6: {'true' if cfg.get('dhcp6', False) else 'false'}",
            ])
            if cfg.get("addresses"):
                lines.append("      addresses:")
                for addr in cfg["addresses"]:
                    lines.append(f"        - \"{addr}\"")
            if cfg.get("nameservers"):
                lines.append("      nameservers:")
                lines.append("        addresses:")
                for dns in cfg["nameservers"]:
                    lines.append(f"          - \"{dns}\"")

        if vlans:
            lines.append("  vlans:")
            for vlan in vlans:
                name = f"{vlan.parent}.{vlan.vlan_id}"
                lines.extend([
                    f"    {name}:",
                    f"      id: {vlan.vlan_id}",
                    f"      link: {vlan.parent}",
                    f"      optional: {'true' if vlan.optional else 'false'}",
                ])
                if vlan.mtu:
                    lines.append(f"      mtu: {vlan.mtu}")
                lines.append(f"      dhcp4: {'true' if vlan.ipv4.mode == 'dhcp' else 'false'}")
                lines.append(f"      dhcp6: {'true' if vlan.ipv6.mode == 'dhcp' else 'false'}")
                if vlan.ipv4.mode == "static":
                    lines.append("      addresses:")
                    lines.append(f"        - \"{vlan.build_ipv4_address()}\"")
                    if vlan.ipv4.gateway:
                        lines.append("      routes:")
                        lines.append("        - to: default")
                        lines.append(f"          via: \"{vlan.ipv4.gateway}\"")
                if vlan.ipv6.mode == "static" and vlan.ipv6.address:
                    lines.append("      addresses:")
                    lines.append(f"        - \"{vlan.ipv6.address}\"")
                if vlan.dns:
                    lines.append("      nameservers:")
                    lines.append("        addresses:")
                    for dns in vlan.dns:
                        lines.append(f"          - \"{dns}\"")
                    if vlan.search:
                        lines.append("        search:")
                        for domain in vlan.search:
                            lines.append(f"          - \"{domain}\"")
        return "\n".join(lines) + "\n"

    def write(self, content: str) -> str:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(self.path, self.backup_dir / f"99-server-menu.yaml.{stamp}.bak")
        self.path.write_text(content, encoding="utf-8")
        return str(self.path)


class MessageDialog(ModalScreen[None]):
    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self.title, id="dialog-title")
            yield Static(self.message)
            yield Button("OK", id="ok")

    @on(Button.Pressed, "#ok")
    def dismiss_dialog(self) -> None:
        self.dismiss(None)


class HostnameScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Hostname Management")
        yield Input(placeholder="New hostname", id="hostname")
        with Horizontal():
            yield Button("Apply", id="apply")
            yield Button("Back", id="back")
        yield Footer()

    @on(Button.Pressed, "#apply")
    def apply_hostname(self) -> None:
        value = self.query_one("#hostname", Input).value.strip()
        app = self.app
        if not Validator.hostname(value):
            app.push_screen(MessageDialog("Error", "Invalid hostname format."))
            return
        ops = app.ops
        res = ops.run(["hostnamectl", "set-hostname", value])
        hosts = Path("/etc/hosts")
        if hosts.exists():
            lines = hosts.read_text(encoding="utf-8").splitlines()
            updated = [l for l in lines if not l.startswith("127.0.1.1")]
            updated.append(f"127.0.1.1\t{value}")
            hosts.write_text("\n".join(updated) + "\n", encoding="utf-8")
        app.push_screen(MessageDialog("Hostname", res.output or "Hostname updated."))

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


class BatchInstallScreen(Screen):
    selected: set[str]

    def __init__(self):
        super().__init__()
        self.selected = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Batch Software Installer")
        options = [(name, name) for name in PACKAGE_GROUPS] + [(f"[Profile] {name}", f"profile::{name}") for name in PROFILES]
        yield Select(options=options, prompt="Select group or profile", id="selector")
        with Horizontal():
            yield Button("Add", id="add")
            yield Button("Clear", id="clear")
            yield Button("Install", id="install")
            yield Button("Back", id="back")
        yield Pretty([], id="batch")
        yield Footer()

    @on(Button.Pressed, "#add")
    def add(self) -> None:
        sel = self.query_one("#selector", Select).value
        if not sel:
            return
        if str(sel).startswith("profile::"):
            profile = str(sel).split("::", 1)[1]
            for group in PROFILES[profile]:
                self.selected.update(PACKAGE_GROUPS[group])
        else:
            self.selected.update(PACKAGE_GROUPS[str(sel)])
        self.query_one("#batch", Pretty).update(sorted(self.selected))

    @on(Button.Pressed, "#clear")
    def clear(self) -> None:
        self.selected.clear()
        self.query_one("#batch", Pretty).update([])

    @on(Button.Pressed, "#install")
    def install(self) -> None:
        if not self.selected:
            self.app.push_screen(MessageDialog("Installer", "Batch is empty."))
            return
        cmd = ["apt-get", "update"]
        self.app.ops.run(cmd)
        result = self.app.ops.run(["apt-get", "install", "-y", *sorted(self.selected)])
        self.app.push_screen(MessageDialog("Installer", result.output or "Install complete."))

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


class FirewallScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            for item in ["enable", "disable", "status", "allow ssh", "allow 80/tcp", "allow 443/tcp"]:
                yield Button(item, id=item.replace(" ", "_"))
            yield Input(placeholder="Custom port e.g. 8443/tcp", id="custom")
            yield Button("Allow custom", id="allow_custom")
            yield Button("Back", id="back")
        yield Footer()

    def do(self, args: list[str]) -> None:
        out = self.app.ops.run(["ufw", *args]).output
        self.app.push_screen(MessageDialog("UFW", out))

    @on(Button.Pressed)
    def click(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "enable":
            self.do(["--force", "enable"])
        elif bid == "disable":
            self.do(["disable"])
        elif bid == "status":
            self.do(["status", "verbose"])
        elif bid == "allow_ssh":
            self.do(["allow", "ssh"])
        elif bid == "allow_80/tcp":
            self.do(["allow", "80/tcp"])
        elif bid == "allow_443/tcp":
            self.do(["allow", "443/tcp"])
        elif bid == "allow_custom":
            value = self.query_one("#custom", Input).value.strip()
            if not re.match(r"^\d{1,5}/(tcp|udp)$", value):
                self.app.push_screen(MessageDialog("UFW", "Invalid custom port format."))
            else:
                self.do(["allow", value])
        elif bid == "back":
            self.app.pop_screen()


class ServicesScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Select(options=[(s, s) for s in COMMON_SERVICES], prompt="Service", id="service")
        with Horizontal():
            for action in ["start", "stop", "restart", "enable", "disable", "status"]:
                yield Button(action, id=action)
            yield Button("Back", id="back")
        yield Footer()

    @on(Button.Pressed)
    def manage(self, event: Button.Pressed) -> None:
        action = event.button.id
        if action == "back":
            self.app.pop_screen()
            return
        svc = str(self.query_one("#service", Select).value)
        if not svc or svc == "None":
            self.app.push_screen(MessageDialog("Service", "Pick a service."))
            return
        out = self.app.ops.run(["systemctl", action, svc]).output
        self.app.push_screen(MessageDialog("Service", out or f"{action} {svc} done"))


class GitSetupScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Git user.name", id="name")
        yield Input(placeholder="Git user.email", id="email")
        yield Input(placeholder="Default branch (main)", id="branch")
        with Horizontal():
            yield Button("Apply", id="apply")
            yield Button("Back", id="back")
        yield Footer()

    @on(Button.Pressed, "#apply")
    def apply(self) -> None:
        if not shutil.which("git"):
            self.app.push_screen(MessageDialog("Git", "Git is not installed."))
            return
        name = self.query_one("#name", Input).value.strip()
        email = self.query_one("#email", Input).value.strip()
        branch = self.query_one("#branch", Input).value.strip() or "main"
        if not name or "@" not in email:
            self.app.push_screen(MessageDialog("Git", "Name and valid email are required."))
            return
        self.app.ops.run(["git", "config", "--global", "user.name", name])
        self.app.ops.run(["git", "config", "--global", "user.email", email])
        out = self.app.ops.run(["git", "config", "--global", "init.defaultBranch", branch]).output
        self.app.push_screen(MessageDialog("Git", out or "Git global config updated."))

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


class JoeConfigScreen(Screen):
    selected_file = "/etc/joe/joerc"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                yield Label("/etc/joe files")
                files = sorted(str(p) for p in Path("/etc/joe").glob("*") if p.is_file())
                lv = ListView(id="files")
                for file in files:
                    lv.append(ListItem(Label(file)))
                yield lv
                yield Button("Toggle option in joerc", id="toggle")
            with Vertical(id="right"):
                yield TextArea(code_editor=False, language="text", id="editor")
                with Horizontal():
                    yield Button("Load", id="load")
                    yield Button("Save", id="save")
                    yield Button("Back", id="back")
        yield Footer()

    @on(ListView.Selected, "#files")
    def pick(self, event: ListView.Selected) -> None:
        label = event.item.query_one(Label)
        self.selected_file = label.renderable

    @on(Button.Pressed, "#load")
    def load(self) -> None:
        path = Path(self.selected_file)
        self.query_one("#editor", TextArea).text = path.read_text(encoding="utf-8")

    @on(Button.Pressed, "#save")
    def save(self) -> None:
        path = Path(self.selected_file)
        path.write_text(self.query_one("#editor", TextArea).text, encoding="utf-8")
        self.app.push_screen(MessageDialog("JOE", f"Saved {path}"))

    @on(Button.Pressed, "#toggle")
    def toggle(self) -> None:
        joerc = Path("/etc/joe/joerc")
        lines = joerc.read_text(encoding="utf-8").splitlines()
        target = "-force"
        toggled = False
        for idx, line in enumerate(lines):
            if line.strip() == target:
                lines[idx] = f"#{target}"
                toggled = True
                break
            if line.strip() == f"#{target}":
                lines[idx] = target
                toggled = True
                break
        if not toggled:
            lines.append(target)
        joerc.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.app.push_screen(MessageDialog("JOE", "Toggled -force in /etc/joe/joerc"))

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


class NetplanScreen(Screen):
    def __init__(self):
        super().__init__()
        self.vlans: list[VLANConfig] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Advanced Netplan & VLAN Configuration")
        yield DataTable(id="ifaces")
        with Horizontal():
            yield Button("Refresh Interfaces", id="refresh")
            yield Button("Add Preset VLAN", id="add_preset")
            yield Button("Add Custom VLAN", id="add_custom")
            yield Button("Save YAML", id="save")
            yield Button("Verify", id="verify")
            yield Button("Try", id="try")
            yield Button("Apply", id="apply")
            yield Button("Back", id="back")
        yield Pretty([], id="vlan_state")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_interfaces()

    def refresh_interfaces(self) -> None:
        table = self.query_one("#ifaces", DataTable)
        table.clear(columns=True)
        table.add_columns("Interface", "State", "Address")
        res = self.app.ops.run(["ip", "-br", "address"])
        for line in res.output.splitlines():
            parts = line.split()
            if not parts or parts[0] == "lo":
                continue
            iface = parts[0]
            state = parts[1] if len(parts) > 1 else "UNKNOWN"
            addr = " ".join(parts[2:]) if len(parts) > 2 else "-"
            table.add_row(iface, state, addr)

    def summarize_vlans(self) -> list[dict[str, Any]]:
        rows = []
        for v in self.vlans:
            rows.append(
                {
                    "name": f"{v.parent}.{v.vlan_id}",
                    "ipv4": v.ipv4.mode,
                    "addr": v.build_ipv4_address() if v.ipv4.mode == "static" else "-",
                    "gw": v.ipv4.gateway,
                    "router": v.router_index,
                    "dns": v.dns,
                }
            )
        return rows

    def ask_vlan(self, custom: bool) -> None:
        parent = "eth0"
        if custom:
            vlan = VLANConfig(vlan_id=400, parent=parent, use_preset=False)
            vlan.ipv4 = IPv4Config(mode="static", address="192.168.50.10/24", gateway="192.168.50.1")
        else:
            preset_id = 250
            p = VLAN_PRESETS[preset_id]
            vlan = VLANConfig(vlan_id=preset_id, parent=parent, use_preset=True, prefix=p["prefix"])
            vlan.ipv4.mode = "static"
            vlan.host_octet = 10
            vlan.router_index = 0
            vlan.ipv4.gateway = p["routers"][0]["gateway"]
        self.vlans.append(vlan)
        self.query_one("#vlan_state", Pretty).update(self.summarize_vlans())

    @on(Button.Pressed)
    def handle(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "refresh":
            self.refresh_interfaces()
        elif bid == "add_preset":
            self.ask_vlan(custom=False)
        elif bid == "add_custom":
            self.ask_vlan(custom=True)
        elif bid == "save":
            manager = NetplanManager(self.app.logger)
            iface_cfg: dict[str, dict[str, Any]] = {}
            content = manager.render(iface_cfg, self.vlans)
            path = manager.write(content)
            self.app.push_screen(MessageDialog("Netplan", f"Saved {path}"))
        elif bid == "verify":
            out = self.app.ops.run(["netplan", "generate"]).output
            self.app.push_screen(MessageDialog("Netplan verify", out or "netplan generate succeeded"))
        elif bid == "try":
            out = self.app.ops.run(["netplan", "try", "--timeout", "30"]).output
            self.app.push_screen(MessageDialog("Netplan try", out))
        elif bid == "apply":
            out = self.app.ops.run(["netplan", "apply"]).output
            self.app.push_screen(MessageDialog("Netplan apply", out))
        elif bid == "back":
            self.app.pop_screen()


class MainMenu(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Minimal Server Menu (Ubuntu 24.04)")
        menu = ListView(id="menu")
        for item in [
            "Hostname Management",
            "Batch Install",
            "Git Setup",
            "UFW Firewall",
            "Service Manager",
            "Advanced Netplan/VLAN",
            "JOE /etc/joe Config",
            "Exit",
        ]:
            menu.append(ListItem(Label(item)))
        yield menu
        yield Footer()

    @on(ListView.Selected, "#menu")
    def open(self, event: ListView.Selected) -> None:
        name = event.item.query_one(Label).renderable
        screens = {
            "Hostname Management": HostnameScreen(),
            "Batch Install": BatchInstallScreen(),
            "Git Setup": GitSetupScreen(),
            "UFW Firewall": FirewallScreen(),
            "Service Manager": ServicesScreen(),
            "Advanced Netplan/VLAN": NetplanScreen(),
            "JOE /etc/joe Config": JoeConfigScreen(),
        }
        if name == "Exit":
            self.app.exit()
            return
        self.app.push_screen(screens[name])


class ServerMenuApp(App[None]):
    CSS = """
    Screen { background: #001f4d; color: #e8f1ff; }
    #dialog { width: 70%; height: auto; border: round #78a6ff; background: #00327a; padding: 1 2; }
    #dialog-title { text-style: bold; color: #d8e6ff; }
    Button { margin: 0 1; }
    """

    def __init__(self):
        super().__init__()
        self.logger = setup_logging()
        self.ops = SystemOps(self.logger)

    def on_mount(self) -> None:
        self._normalize_resolver()
        self.push_screen(MainMenu())

    def _normalize_resolver(self) -> None:
        resolv = Path("/etc/resolv.conf")
        lines = [f"nameserver {dns}" for dns in PUBLIC_DNS]
        try:
            if resolv.exists() or resolv.is_symlink():
                resolv.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.logger.info("resolv.conf overwritten with public DNS list")
        except Exception:
            self.logger.exception("failed to update resolv.conf")


if __name__ == "__main__":
    ServerMenuApp().run()
