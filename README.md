# sshtui

A small terminal UI for managing SSH host aliases with key-based (passwordless) auth.

- **Add new SSH connection**: enter an alias + `user@host[:port]`. It reuses (or generates)
  `~/.ssh/id_ed25519` / `.pub`, runs `ssh-copy-id` so you type your password into its own
  normal prompt (sshtui never sees or stores it), then appends a `Host` block to
  `~/.ssh/config` on success.
- **List / connect to aliases**: search-as-you-type over saved `Host` entries in
  `~/.ssh/config`, then Enter to `ssh` in.
- **Edit an alias**: rename an alias or change its host/user/port after the fact.
- **Language**: toggle English / 日本語 from the main menu; the choice is remembered.

Each alias gets its own `~/.ssh/known_hosts.d/<alias>` file instead of sharing the global
`~/.ssh/known_hosts`, so two aliases pointing at the same address (e.g. two vehicles that
reuse an IP) never collide over a cached host fingerprint. If a saved alias's host key
changes or isn't trusted yet, sshtui detects it before connecting and offers to fix it.

## Requirements

Only the Python standard library is used (curses, subprocess, etc.) plus the system
`ssh` / `ssh-keygen` / `ssh-copy-id` binaries. To check/install those:

```bash
./build_deps.sh
```

## Running it

After setup (see below), just run:

```bash
configssh
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
./install.sh                    # wires up the configssh command, wherever this repo lives
```

`install.sh` creates `~/.local/bin/configssh`, pointing at this repo's actual location, and
warns if `~/.local/bin` isn't already on your `PATH`. Then run `configssh` from any terminal.
