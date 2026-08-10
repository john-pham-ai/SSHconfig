# sshtui

A small terminal UI for managing SSH host aliases with key-based (passwordless) auth.

- **Add new SSH connection**: enter an alias + `user@host[:port]`. It reuses (or generates)
  `~/.ssh/id_ed25519` / `.pub`, runs `ssh-copy-id` so you type your password into its own
  normal prompt (sshtui never sees or stores it), then appends a `Host` block to
  `~/.ssh/config` on success.
- **List / connect to aliases**: reads `Host` entries from `~/.ssh/config` and lets you
  pick one to `ssh` into.

## Requirements

Only the Python standard library is used (curses, subprocess, etc.) plus the system
`ssh` / `ssh-keygen` / `ssh-copy-id` binaries. To check/install those:

```bash
./build_deps.sh
```

## Running it

After setup (see below), just run:

```bash
sshtui
```

Or directly without the alias:

```bash
python3 ~/sshtui/sshtui.py
```

## One-time setup on a new machine

```bash
git clone <your-repo-url> ~/SSHconfig   # any path is fine
cd ~/SSHconfig
./build_deps.sh                 # checks/installs ssh tooling
./install.sh                    # wires up the sshtui alias, wherever this repo lives
```

`install.sh` creates `~/.local/bin/sshtui`, pointing at this repo's actual location, and
warns if `~/.local/bin` isn't already on your `PATH`. Then run `sshtui` from any terminal.
