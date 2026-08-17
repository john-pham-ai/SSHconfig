#!/usr/bin/env python3
"""SSH config TUI: add host aliases with key-based auth, and connect via saved aliases.

Workflow for "add":
  1. You enter an address (user@host, optional :port) and an alias name.
  2. If ~/.ssh/id_ed25519(.pub) doesn't exist yet, it's generated (no passphrase).
  3. ssh-copy-id runs to install the public key on the remote host. You type the
     remote password directly into ssh-copy-id's own prompt -- this tool never
     reads, stores, or transmits your password itself.
  4. On success, a Host block is appended to ~/.ssh/config using that key, so
     future `ssh <alias>` connections are passwordless.
"""

import curses
import os
import re
import subprocess
import sys

SSH_DIR = os.path.expanduser("~/.ssh")
CONFIG_PATH = os.path.join(SSH_DIR, "config")
KEY_PATH = os.path.join(SSH_DIR, "id_ed25519")
PUB_KEY_PATH = KEY_PATH + ".pub"
KNOWN_HOSTS_DIR = os.path.join(SSH_DIR, "known_hosts.d")


def known_hosts_path(alias):
    # Per-alias known_hosts file: multiple aliases sharing one IP (e.g. two
    # vehicles reusing the same address) each get their own host-key memory,
    # so one vehicle's fingerprint never collides with another's.
    return os.path.join(KNOWN_HOSTS_DIR, alias)


# ---------------------------------------------------------------------------
# ssh config parsing / writing
# ---------------------------------------------------------------------------

def ensure_ssh_dir():
    os.makedirs(SSH_DIR, mode=0o700, exist_ok=True)
    os.chmod(SSH_DIR, 0o700)


def read_hosts():
    """Return list of dicts: {alias, hostname, user, port} parsed from ~/.ssh/config."""
    if not os.path.exists(CONFIG_PATH):
        return []
    hosts = []
    current = None
    with open(CONFIG_PATH) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            key, value = parts[0].lower(), parts[1].strip()
            if key == "host":
                if "*" in value or "?" in value:
                    current = None
                    continue
                current = {"alias": value, "hostname": value, "user": None, "port": None}
                hosts.append(current)
            elif current is None:
                continue
            elif key == "hostname":
                current["hostname"] = value
            elif key == "user":
                current["user"] = value
            elif key == "port":
                current["port"] = value
    return hosts


def alias_exists(alias):
    return any(h["alias"] == alias for h in read_hosts())


def find_host_block(lines, alias):
    """Return (start, end) line-index range of the `Host <alias>` block, or (None, None)."""
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None and re.match(rf"(?i)^host\s+{re.escape(alias)}\s*$", stripped):
            start = i
            continue
        if start is not None and re.match(r"(?i)^host\s+\S+", stripped):
            end = i
            break
    return (start, end) if start is not None else (None, None)


def rewrite_host_entry(old_alias, new_alias, hostname, user, port):
    with open(CONFIG_PATH) as f:
        lines = f.readlines()

    start, end = find_host_block(lines, old_alias)
    if start is None:
        raise ValueError(f"Alias '{old_alias}' not found in {CONFIG_PATH}")

    new_kh_path = known_hosts_path(new_alias)
    block = [f"Host {new_alias}\n", f"    HostName {hostname}\n"]
    if user:
        block.append(f"    User {user}\n")
    if port:
        block.append(f"    Port {port}\n")
    block.append(f"    IdentityFile {KEY_PATH}\n")
    block.append("    IdentitiesOnly yes\n")
    block.append(f"    UserKnownHostsFile {new_kh_path}\n")

    lines[start:end] = block
    with open(CONFIG_PATH, "w") as f:
        f.writelines(lines)
    os.chmod(CONFIG_PATH, 0o600)

    old_kh_path = known_hosts_path(old_alias)
    if new_alias != old_alias and os.path.exists(old_kh_path) and not os.path.exists(new_kh_path):
        os.rename(old_kh_path, new_kh_path)


def append_host_entry(alias, hostname, user, port):
    ensure_ssh_dir()
    os.makedirs(KNOWN_HOSTS_DIR, mode=0o700, exist_ok=True)
    lines = [f"Host {alias}", f"    HostName {hostname}"]
    if user:
        lines.append(f"    User {user}")
    if port:
        lines.append(f"    Port {port}")
    lines.append(f"    IdentityFile {KEY_PATH}")
    lines.append("    IdentitiesOnly yes")
    lines.append(f"    UserKnownHostsFile {known_hosts_path(alias)}")
    block = "\n".join(lines) + "\n"

    is_new = not os.path.exists(CONFIG_PATH)
    with open(CONFIG_PATH, "a") as f:
        if not is_new:
            f.write("\n")
        f.write(block)
    os.chmod(CONFIG_PATH, 0o600)


# ---------------------------------------------------------------------------
# key + ssh-copy-id
# ---------------------------------------------------------------------------

def keypair_exists():
    return os.path.exists(KEY_PATH) and os.path.exists(PUB_KEY_PATH)


def generate_keypair():
    ensure_ssh_dir()
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", KEY_PATH, "-C", "sshtui-generated"],
        check=True,
        stdout=subprocess.DEVNULL,
    )


ADDRESS_RE = re.compile(
    r"^(?:(?P<user>[^@]+)@)?(?P<host>[^:\s]+)(?::(?P<port>\d+))?$"
)


def parse_address(address):
    m = ADDRESS_RE.match(address.strip())
    if not m:
        return None
    return m.group("user"), m.group("host"), m.group("port")


def run_ssh_copy_id(alias, user, hostname, port):
    os.makedirs(KNOWN_HOSTS_DIR, mode=0o700, exist_ok=True)
    target = f"{user}@{hostname}" if user else hostname
    cmd = [
        "ssh-copy-id", "-i", PUB_KEY_PATH,
        "-o", f"UserKnownHostsFile={known_hosts_path(alias)}",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if port:
        cmd += ["-p", port]
    cmd.append(target)
    # Inherits the real terminal so ssh-copy-id can prompt for the password itself.
    result = subprocess.run(cmd)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# host key preflight / repair
# ---------------------------------------------------------------------------

def preflight_ssh(alias, extra_opts=None):
    """Non-interactive connectivity probe. Returns (ok, combined_output)."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if extra_opts:
        for opt in extra_opts:
            cmd += ["-o", opt]
    cmd += [alias, "exit"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def ensure_host_trust(stdscr, alias, hostname):
    """Detect a host-key mismatch/unknown-host error for this alias and offer
    to repair it before the real interactive connection. Returns True to
    proceed with the normal connect attempt, False to abort."""
    ok, output = preflight_ssh(alias)
    if ok:
        return True

    changed = "IDENTIFICATION HAS CHANGED" in output.upper() or "REMOTE HOST IDENTIFICATION HAS CHANGED" in output
    unknown = (not changed) and ("Host key verification failed" in output or "no matching host key" in output.lower())

    if not (changed or unknown):
        # Some other failure (auth, network, etc) -- not a key issue, let the
        # real ssh attempt show its own error naturally.
        return True

    detail_lines = [l for l in output.strip().splitlines() if l.strip()][-6:]
    if changed:
        header = [
            f"Host key CHANGED for alias '{alias}' ({hostname}).",
            "A different machine now appears to be answering at this address.",
            "",
        ]
    else:
        header = [
            f"Host key for alias '{alias}' ({hostname}) is not yet trusted.",
            "",
        ]
    stdscr.erase()
    for i, line in enumerate(header + detail_lines):
        safe_addstr(stdscr, i, 2, line)
    h, _ = stdscr.getmaxyx()
    safe_addstr(stdscr, h - 1, 2, "Press 'y' to trust the new key and retry, any other key to cancel", curses.A_DIM)
    stdscr.refresh()
    key = stdscr.getch()
    if key not in (ord("y"), ord("Y")):
        return False

    kh_path = known_hosts_path(alias)
    if changed and os.path.exists(kh_path):
        subprocess.run(["ssh-keygen", "-R", hostname, "-f", kh_path], capture_output=True)
        subprocess.run(["ssh-keygen", "-R", alias, "-f", kh_path], capture_output=True)

    ok2, output2 = preflight_ssh(alias, extra_opts=["StrictHostKeyChecking=accept-new"])
    if ok2:
        message_screen(stdscr, [f"Key for '{alias}' trusted. Connecting..."], wait_key=False)
    else:
        message_screen(stdscr, ["Could not automatically fix it:"] + output2.strip().splitlines()[-6:])
    return True


# ---------------------------------------------------------------------------
# curses helpers
# ---------------------------------------------------------------------------

def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if 0 <= y < h:
        try:
            stdscr.addstr(y, x, text[: max(0, w - x - 1)], attr)
        except curses.error:
            pass


def menu(stdscr, title, options, footer="Up/Down to move, Enter to select, q to quit"):
    idx = 0
    curses.curs_set(0)
    while True:
        stdscr.erase()
        safe_addstr(stdscr, 0, 2, title, curses.A_BOLD)
        for i, opt in enumerate(options):
            attr = curses.A_REVERSE if i == idx else 0
            safe_addstr(stdscr, 2 + i, 4, opt, attr)
        h, _ = stdscr.getmaxyx()
        safe_addstr(stdscr, h - 1, 2, footer, curses.A_DIM)
        stdscr.refresh()
        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(options)
        elif key in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(options)
        elif key in (curses.KEY_ENTER, 10, 13):
            return idx
        elif key in (ord("q"), 27):  # q or Esc
            return None


def text_input(stdscr, prompt, y=2):
    curses.curs_set(1)
    curses.echo()
    stdscr.erase()
    safe_addstr(stdscr, 0, 2, prompt, curses.A_BOLD)
    safe_addstr(stdscr, y, 2, "> ")
    stdscr.refresh()
    win = curses.newwin(1, curses.COLS - 6, y, 4)
    win.refresh()
    try:
        value = win.getstr().decode("utf-8", errors="ignore")
    except Exception:
        value = ""
    curses.noecho()
    curses.curs_set(0)
    return value.strip()


def message_screen(stdscr, lines, wait_key=True):
    stdscr.erase()
    for i, line in enumerate(lines):
        safe_addstr(stdscr, i, 2, line)
    if wait_key:
        h, _ = stdscr.getmaxyx()
        safe_addstr(stdscr, min(h - 1, len(lines) + 1), 2, "Press any key to continue...", curses.A_DIM)
        stdscr.refresh()
        stdscr.getch()
    else:
        stdscr.refresh()


def suspend_curses_and_run(stdscr, fn):
    """Drop out of curses to a normal terminal, run fn(), then resume curses."""
    curses.def_prog_mode()
    curses.endwin()
    try:
        result = fn()
    finally:
        stdscr.refresh()
        curses.reset_prog_mode()
        curses.curs_set(0)
    return result


# ---------------------------------------------------------------------------
# screens
# ---------------------------------------------------------------------------

def screen_add_host(stdscr):
    alias = text_input(stdscr, "New alias name (e.g. myserver):")
    if not alias:
        return
    if alias_exists(alias):
        message_screen(stdscr, [f"Alias '{alias}' already exists in ~/.ssh/config.", "Pick a different name."])
        return

    address = text_input(stdscr, "Address to connect to (user@host or user@host:port):")
    if not address:
        return
    parsed = parse_address(address)
    if not parsed:
        message_screen(stdscr, [f"Could not parse address: {address}"])
        return
    user, hostname, port = parsed

    if not keypair_exists():
        message_screen(stdscr, ["No ~/.ssh/id_ed25519 keypair found.", "Generating one now (no passphrase)..."], wait_key=False)

        def do_gen():
            print("Generating ed25519 keypair at", KEY_PATH)
            generate_keypair()

        try:
            suspend_curses_and_run(stdscr, do_gen)
        except subprocess.CalledProcessError as e:
            message_screen(stdscr, [f"Key generation failed: {e}"])
            return

    def do_copy():
        print(f"Installing public key on {user + '@' if user else ''}{hostname}")
        print("Enter the account password when prompted below.")
        print("-" * 60)
        return run_ssh_copy_id(alias, user, hostname, port)

    ok = suspend_curses_and_run(stdscr, do_copy)

    if not ok:
        message_screen(stdscr, [
            "ssh-copy-id did not succeed (wrong password, host unreachable, etc).",
            "No entry was added to ~/.ssh/config.",
        ])
        return

    append_host_entry(alias, hostname, user, port)
    message_screen(stdscr, [
        f"Success! Added alias '{alias}' to ~/.ssh/config.",
        f"You can now connect any time with:  ssh {alias}",
    ])


def screen_list_hosts(stdscr):
    while True:
        hosts = read_hosts()
        if not hosts:
            message_screen(stdscr, ["No aliases found in ~/.ssh/config yet.", "Add one from the main menu first."])
            return

        options = [
            f"{h['alias']:<20} -> {(h['user'] + '@') if h['user'] else ''}{h['hostname']}" + (f":{h['port']}" if h['port'] else "")
            for h in hosts
        ] + ["<- Back"]

        choice = menu(stdscr, "Saved SSH aliases (Enter to connect)", options)
        if choice is None or choice == len(hosts):
            return

        alias = hosts[choice]["alias"]
        hostname = hosts[choice]["hostname"]

        if not ensure_host_trust(stdscr, alias, hostname):
            continue

        def do_connect():
            print(f"Connecting: ssh {alias}")
            print("-" * 60)
            subprocess.run(["ssh", alias])

        suspend_curses_and_run(stdscr, do_connect)
        message_screen(stdscr, ["Session ended."])


def screen_edit_host(stdscr):
    hosts = read_hosts()
    if not hosts:
        message_screen(stdscr, ["No aliases found in ~/.ssh/config yet.", "Add one from the main menu first."])
        return

    options = [
        f"{h['alias']:<20} -> {(h['user'] + '@') if h['user'] else ''}{h['hostname']}" + (f":{h['port']}" if h['port'] else "")
        for h in hosts
    ] + ["<- Back"]
    choice = menu(stdscr, "Edit alias (Enter to select)", options)
    if choice is None or choice == len(hosts):
        return

    old = hosts[choice]

    def with_default(prompt, current):
        current_label = current if current else "(none)"
        value = text_input(stdscr, f"{prompt} [current: {current_label}, blank = keep]:")
        return value if value else current

    new_alias = with_default("Alias name", old["alias"])
    if new_alias != old["alias"] and alias_exists(new_alias):
        message_screen(stdscr, [f"Alias '{new_alias}' already exists. No changes made."])
        return

    new_hostname = with_default("Address/host", old["hostname"])
    new_user = with_default("User", old["user"])
    new_port = with_default("Port", old["port"])

    try:
        rewrite_host_entry(old["alias"], new_alias, new_hostname, new_user, new_port)
    except ValueError as e:
        message_screen(stdscr, [f"Failed to update: {e}"])
        return

    message_screen(stdscr, [
        f"Updated alias '{old['alias']}' -> '{new_alias}'.",
        f"Connect any time with:  ssh {new_alias}",
    ])


def main(stdscr):
    curses.curs_set(0)
    while True:
        choice = menu(stdscr, "SSH Config Manager", [
            "Add new SSH connection",
            "List / connect to aliases",
            "Edit an alias",
            "Quit",
        ])
        if choice is None or choice == 3:
            return
        elif choice == 0:
            screen_add_host(stdscr)
        elif choice == 1:
            screen_list_hosts(stdscr)
        elif choice == 2:
            screen_edit_host(stdscr)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        sys.exit(0)
