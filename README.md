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
configssh
```

Or directly without the alias:

```bash
python3 ~/sshtui/sshtui.py
```

## One-time setup on a new machine

```bash
git clone <your-repo-url> ~/sshtui
cd ~/sshtui
./build_deps.sh                 # checks/installs ssh tooling
chmod +x sshtui.py build_deps.sh
mkdir -p ~/.local/bin
printf '#!/usr/bin/env bash\nexec python3 "$HOME/sshtui/sshtui.py" "$@"\n' > ~/.local/bin/configssh
chmod +x ~/.local/bin/configssh
# Make sure ~/.local/bin is on PATH (add to ~/.bashrc if not):
#   export PATH="$HOME/.local/bin:$PATH"
```

Then run `configssh` from any terminal.
