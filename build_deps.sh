#!/usr/bin/env bash
# Checks for / installs everything sshtui.py needs to run.
# sshtui.py itself only uses the Python standard library, so the real
# dependencies here are system binaries: python3 (with curses), ssh,
# ssh-keygen, and ssh-copy-id (all normally shipped in openssh-client).

set -euo pipefail

missing=()

command -v python3 >/dev/null 2>&1 || missing+=("python3")
python3 -c "import curses" >/dev/null 2>&1 || missing+=("python3-curses (bundled with python3 on most distros)")
command -v ssh >/dev/null 2>&1 || missing+=("openssh-client")
command -v ssh-keygen >/dev/null 2>&1 || missing+=("openssh-client")
command -v ssh-copy-id >/dev/null 2>&1 || missing+=("openssh-client")

if [ ${#missing[@]} -eq 0 ]; then
  echo "All dependencies already installed."
  exit 0
fi

echo "Missing: ${missing[*]}"

if command -v apt-get >/dev/null 2>&1; then
  echo "Installing via apt-get (will prompt for sudo password)..."
  sudo apt-get update
  sudo apt-get install -y python3 openssh-client
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 openssh-clients
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --noconfirm python openssh
elif command -v brew >/dev/null 2>&1; then
  brew install python openssh
else
  echo "No supported package manager found (apt-get/dnf/pacman/brew)."
  echo "Please install manually: python3 (with curses) and openssh-client."
  exit 1
fi

echo "Done. Re-run this script to verify."
