# Minimal Server Menu (Ubuntu 24.04)

Terminal-native server management suite built with Python + Textual.

## Features

- Blue-themed TUI designed for SSH/console use.
- Command logging with fallback from `./error.log` to `/var/log/server-menu.error.log`.
- Hostname management with RFC-style validation and `/etc/hosts` updates.
- Batch package installation with groups and profiles.
- Git global setup assistant (`user.name`, `user.email`, default branch).
- UFW management workflows.
- `systemctl` service manager.
- Netplan + VLAN workflow with:
  - Built-in presets for VLANs 2,3,5,10,99,250,251,300-306.
  - VLAN 250 multi-router model (single router selection in data model).
  - Custom VLAN support.
  - YAML generation to `/etc/netplan/99-server-menu.yaml`.
  - Backup support under `/etc/netplan/.server-menu-backups/`.
  - Verify/Try/Apply hooks.
- JOE editor management screen for `/etc/joe/*` and `joerc` option toggling.
- Startup DNS normalization that writes the 8 public resolvers into `/etc/resolv.conf`.

## Run

```bash
python3 server_menu.py
```

## Dependency

```bash
pip install textual
```
