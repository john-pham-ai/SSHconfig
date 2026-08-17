#!/usr/bin/env bash
# Installs the configssh launcher, regardless of where this repo was cloned.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

chmod +x "$REPO_DIR/sshtui.py" "$REPO_DIR/build_deps.sh"

mkdir -p "$BIN_DIR"
printf '#!/usr/bin/env bash\nexec python3 "%s/sshtui.py" "$@"\n' "$REPO_DIR" > "$BIN_DIR/configssh"
chmod +x "$BIN_DIR/configssh"

echo "Installed configssh -> $BIN_DIR/configssh (running $REPO_DIR/sshtui.py)"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "Note: $BIN_DIR is not on your PATH."
    echo '  Add this to your shell rc: export PATH="$HOME/.local/bin:$PATH"'
    ;;
esac
