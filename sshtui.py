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


def append_host_entry(alias, hostname, user, port):
    ensure_ssh_dir()
    lines = [f"Host {alias}", f"    HostName {hostname}"]
    if user:
        lines.append(f"    User {user}")
    if port:
        lines.append(f"    Port {port}")
    lines.append(f"    IdentityFile {KEY_PATH}")
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


def run_ssh_copy_id(user, hostname, port):
    target = f"{user}@{hostname}" if user else hostname
    cmd = ["ssh-copy-id", "-i", PUB_KEY_PATH, "-o", "ConnectTimeout=10"]
    if port:
        cmd += ["-p", port]
    cmd.append(target)
    # Inherits the real terminal so ssh-copy-id can prompt for the password itself.
    result = subprocess.run(cmd)
    return result.returncode


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
    """Returns the entered text, or None if the user pressed Esc to go back."""
    curses.curs_set(1)
    stdscr.erase()
    safe_addstr(stdscr, 0, 2, prompt, curses.A_BOLD)
    h, _ = stdscr.getmaxyx()
    safe_addstr(stdscr, h - 1, 2, "Enter to submit, Esc to go back", curses.A_DIM)
    safe_addstr(stdscr, y, 2, "> ")
    stdscr.refresh()
    win = curses.newwin(1, curses.COLS - 6, y, 4)
    win.keypad(True)
    value = ""
    while True:
        win.erase()
        try:
            win.addstr(0, 0, value[: curses.COLS - 7])
        except curses.error:
            pass
        win.refresh()
        key = win.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            break
        elif key == 27:  # Esc
            curses.curs_set(0)
            return None
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            value = value[:-1]
        elif 0 <= key < 256:
            ch = chr(key)
            if ch.isprintable():
                value += ch
    curses.curs_set(0)
    return value.strip()


def search_menu(stdscr, title, items, display_fn,
                 footer="Type to search, Up/Down to move, Enter to select, Esc to go back"):
    """Interactive filter-as-you-type picker. Returns the selected item, or None
    if the user went back (Esc) without selecting anything."""
    query = ""
    idx = 0
    curses.curs_set(1)
    while True:
        filtered = [it for it in items if query.lower() in display_fn(it).lower()]
        if idx >= len(filtered):
            idx = max(0, len(filtered) - 1)
        stdscr.erase()
        safe_addstr(stdscr, 0, 2, title, curses.A_BOLD)
        safe_addstr(stdscr, 1, 2, f"Search: {query}")
        if not filtered:
            safe_addstr(stdscr, 3, 4, "(no matches)", curses.A_DIM)
        for i, it in enumerate(filtered):
            attr = curses.A_REVERSE if i == idx else 0
            safe_addstr(stdscr, 3 + i, 4, display_fn(it), attr)
        h, _ = stdscr.getmaxyx()
        safe_addstr(stdscr, h - 1, 2, footer, curses.A_DIM)
        try:
            stdscr.move(1, min(curses.COLS - 1, 2 + len("Search: ") + len(query)))
        except curses.error:
            pass
        stdscr.refresh()
        key = stdscr.getch()
        if key in (curses.KEY_UP, curses.KEY_BTAB):
            idx = (idx - 1) % len(filtered) if filtered else 0
        elif key == curses.KEY_DOWN:
            idx = (idx + 1) % len(filtered) if filtered else 0
        elif key in (curses.KEY_ENTER, 10, 13):
            if filtered:
                curses.curs_set(0)
                return filtered[idx]
        elif key == 27:  # Esc
            curses.curs_set(0)
            return None
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            query = query[:-1]
        elif 0 <= key < 256:
            ch = chr(key)
            if ch.isprintable():
                query += ch


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
        return run_ssh_copy_id(user, hostname, port)

    returncode = suspend_curses_and_run(stdscr, do_copy)

    if returncode != 0:
        target = f"{user + '@' if user else ''}{hostname}"
        message_screen(stdscr, [
            f"Error: unable to connect to '{target}' (timed out after ~10s per attempt, or unreachable).",
            "Could also be a wrong password. No entry was added to ~/.ssh/config.",
        ])
        return

    append_host_entry(alias, hostname, user, port)
    message_screen(stdscr, [
        f"Success! Added alias '{alias}' to ~/.ssh/config.",
        f"You can now connect any time with:  ssh {alias}",
    ])


def _host_display(h):
    target = f"{(h['user'] + '@') if h['user'] else ''}{h['hostname']}"
    if h["port"]:
        target += f":{h['port']}"
    return f"{h['alias']:<20} -> {target}"


def screen_list_hosts(stdscr):
    while True:
        hosts = read_hosts()
        if not hosts:
            message_screen(stdscr, ["No aliases found in ~/.ssh/config yet.", "Add one from the main menu first."])
            return

        chosen = search_menu(stdscr, "Saved SSH aliases (search + Enter to connect)", hosts, _host_display)
        if chosen is None:
            return

        alias = chosen["alias"]

        def do_connect():
            print(f"Connecting: ssh -o ConnectTimeout=10 {alias}")
            print("-" * 60)
            result = subprocess.run(["ssh", "-o", "ConnectTimeout=10", alias])
            return result.returncode

        returncode = suspend_curses_and_run(stdscr, do_connect)
        if returncode == 255:
            message_screen(stdscr, [f"Error: unable to connect to '{alias}' (timed out after 10s or unreachable)."])
        else:
            message_screen(stdscr, ["Session ended."])


def main(stdscr):
    curses.curs_set(0)
    while True:
        choice = menu(stdscr, "SSH Config Manager", [
            "Add new SSH connection",
            "List / connect to aliases",
            "Quit",
        ])
        if choice is None or choice == 2:
            return
        elif choice == 0:
            screen_add_host(stdscr)
        elif choice == 1:
            screen_list_hosts(stdscr)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        sys.exit(0)
