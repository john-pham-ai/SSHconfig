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
import locale
import os
import re
import subprocess
import sys

SSH_DIR = os.path.expanduser("~/.ssh")
CONFIG_PATH = os.path.join(SSH_DIR, "config")
KEY_PATH = os.path.join(SSH_DIR, "id_ed25519")
PUB_KEY_PATH = KEY_PATH + ".pub"

LANG_CONFIG_PATH = os.path.expanduser("~/.config/sshtui/lang")
LANG_NAMES = {"en": "English", "ja": "日本語"}

STRINGS = {
    "en": {
        "title": "SSH Config Manager",
        "opt_add": "Add new SSH connection",
        "opt_list": "List / connect to aliases",
        "opt_lang": "Language: {name}",
        "opt_quit": "Quit",
        "menu_footer": "Up/Down to move, Enter to select, q to quit",
        "input_footer": "Enter to submit, Esc to go back",
        "prompt_alias": "New alias name (e.g. myserver):",
        "alias_exists": "Alias '{alias}' already exists in ~/.ssh/config.",
        "pick_different_name": "Pick a different name.",
        "prompt_address": "Address to connect to (user@host or user@host:port):",
        "could_not_parse": "Could not parse address: {address}",
        "no_keypair": "No ~/.ssh/id_ed25519 keypair found.",
        "generating_keypair": "Generating one now (no passphrase)...",
        "generating_keypair_at": "Generating ed25519 keypair at {path}",
        "key_gen_failed": "Key generation failed: {error}",
        "installing_key_on": "Installing public key on {target}",
        "enter_password": "Enter the account password when prompted below.",
        "add_error1": "Error: unable to connect to '{target}' (timed out after ~10s per attempt, or unreachable).",
        "add_error2": "Could also be a wrong password. No entry was added to ~/.ssh/config.",
        "add_success1": "Success! Added alias '{alias}' to ~/.ssh/config.",
        "add_success2": "You can now connect any time with:  ssh {alias}",
        "no_aliases": "No aliases found in ~/.ssh/config yet.",
        "add_one_first": "Add one from the main menu first.",
        "search_title": "Saved SSH aliases (search + Enter to connect)",
        "search_label": "Search: ",
        "search_footer": "Type to search, Up/Down to move, Enter to select, Esc to go back",
        "no_matches": "(no matches)",
        "connecting": "Connecting: ssh -o ConnectTimeout=10 {alias}",
        "connect_error": "Error: unable to connect to '{alias}' (timed out after 10s or unreachable).",
        "session_ended": "Session ended.",
        "press_any_key": "Press any key to continue...",
    },
    "ja": {
        "title": "SSH 設定マネージャー",
        "opt_add": "新しい SSH 接続を追加",
        "opt_list": "エイリアス一覧 / 接続",
        "opt_lang": "言語: {name}",
        "opt_quit": "終了",
        "menu_footer": "↑/↓ で移動, Enter で選択, q で終了",
        "input_footer": "Enter で送信, Esc で戻る",
        "prompt_alias": "新しいエイリアス名 (例: myserver):",
        "alias_exists": "エイリアス '{alias}' は ~/.ssh/config に既に存在します。",
        "pick_different_name": "別の名前を指定してください。",
        "prompt_address": "接続先アドレス (user@host または user@host:port):",
        "could_not_parse": "アドレスを解析できませんでした: {address}",
        "no_keypair": "~/.ssh/id_ed25519 の鍵ペアが見つかりません。",
        "generating_keypair": "鍵ペアを生成しています (パスフレーズなし)...",
        "generating_keypair_at": "ed25519 鍵ペアを {path} に生成中",
        "key_gen_failed": "鍵の生成に失敗しました: {error}",
        "installing_key_on": "{target} に公開鍵をインストール中",
        "enter_password": "以下のプロンプトにアカウントのパスワードを入力してください。",
        "add_error1": "エラー: '{target}' に接続できません (試行ごとに約10秒でタイムアウト、または到達不可)。",
        "add_error2": "パスワードが間違っている可能性もあります。~/.ssh/config にエントリは追加されませんでした。",
        "add_success1": "成功! エイリアス '{alias}' を ~/.ssh/config に追加しました。",
        "add_success2": "これで ssh {alias} でいつでも接続できます。",
        "no_aliases": "~/.ssh/config にエイリアスがまだありません。",
        "add_one_first": "まずメインメニューから追加してください。",
        "search_title": "保存済み SSH エイリアス (検索して Enter で接続)",
        "search_label": "検索: ",
        "search_footer": "入力して検索, ↑/↓ で移動, Enter で選択, Esc で戻る",
        "no_matches": "(一致なし)",
        "connecting": "接続中: ssh -o ConnectTimeout=10 {alias}",
        "connect_error": "エラー: '{alias}' に接続できません (10秒でタイムアウト、または到達不可)。",
        "session_ended": "セッションが終了しました。",
        "press_any_key": "何かキーを押して続行...",
    },
}

_current_lang = "en"


def load_lang():
    global _current_lang
    try:
        with open(LANG_CONFIG_PATH) as f:
            value = f.read().strip()
    except FileNotFoundError:
        return
    if value in STRINGS:
        _current_lang = value


def save_lang(lang):
    global _current_lang
    _current_lang = lang
    os.makedirs(os.path.dirname(LANG_CONFIG_PATH), exist_ok=True)
    with open(LANG_CONFIG_PATH, "w") as f:
        f.write(lang)


def t(key, **kwargs):
    text = STRINGS[_current_lang][key]
    return text.format(**kwargs) if kwargs else text


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


def menu(stdscr, title, options, footer=None):
    if footer is None:
        footer = t("menu_footer")
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
    safe_addstr(stdscr, h - 1, 2, t("input_footer"), curses.A_DIM)
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


def search_menu(stdscr, title, items, display_fn, footer=None):
    """Interactive filter-as-you-type picker. Returns the selected item, or None
    if the user went back (Esc) without selecting anything."""
    if footer is None:
        footer = t("search_footer")
    search_label = t("search_label")
    query = ""
    idx = 0
    curses.curs_set(1)
    while True:
        filtered = [it for it in items if query.lower() in display_fn(it).lower()]
        if idx >= len(filtered):
            idx = max(0, len(filtered) - 1)
        stdscr.erase()
        safe_addstr(stdscr, 0, 2, title, curses.A_BOLD)
        safe_addstr(stdscr, 1, 2, f"{search_label}{query}")
        if not filtered:
            safe_addstr(stdscr, 3, 4, t("no_matches"), curses.A_DIM)
        for i, it in enumerate(filtered):
            attr = curses.A_REVERSE if i == idx else 0
            safe_addstr(stdscr, 3 + i, 4, display_fn(it), attr)
        h, _ = stdscr.getmaxyx()
        safe_addstr(stdscr, h - 1, 2, footer, curses.A_DIM)
        try:
            stdscr.move(1, min(curses.COLS - 1, 2 + len(search_label) + len(query)))
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
        safe_addstr(stdscr, min(h - 1, len(lines) + 1), 2, t("press_any_key"), curses.A_DIM)
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
    alias = text_input(stdscr, t("prompt_alias"))
    if not alias:
        return
    if alias_exists(alias):
        message_screen(stdscr, [t("alias_exists", alias=alias), t("pick_different_name")])
        return

    address = text_input(stdscr, t("prompt_address"))
    if not address:
        return
    parsed = parse_address(address)
    if not parsed:
        message_screen(stdscr, [t("could_not_parse", address=address)])
        return
    user, hostname, port = parsed

    if not keypair_exists():
        message_screen(stdscr, [t("no_keypair"), t("generating_keypair")], wait_key=False)

        def do_gen():
            print(t("generating_keypair_at", path=KEY_PATH))
            generate_keypair()

        try:
            suspend_curses_and_run(stdscr, do_gen)
        except subprocess.CalledProcessError as e:
            message_screen(stdscr, [t("key_gen_failed", error=e)])
            return

    def do_copy():
        target_label = f"{user + '@' if user else ''}{hostname}"
        print(t("installing_key_on", target=target_label))
        print(t("enter_password"))
        print("-" * 60)
        return run_ssh_copy_id(user, hostname, port)

    returncode = suspend_curses_and_run(stdscr, do_copy)

    if returncode != 0:
        target = f"{user + '@' if user else ''}{hostname}"
        message_screen(stdscr, [
            t("add_error1", target=target),
            t("add_error2"),
        ])
        return

    append_host_entry(alias, hostname, user, port)
    message_screen(stdscr, [
        t("add_success1", alias=alias),
        t("add_success2", alias=alias),
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
            message_screen(stdscr, [t("no_aliases"), t("add_one_first")])
            return

        chosen = search_menu(stdscr, t("search_title"), hosts, _host_display)
        if chosen is None:
            return

        alias = chosen["alias"]

        def do_connect():
            print(t("connecting", alias=alias))
            print("-" * 60)
            result = subprocess.run(["ssh", "-o", "ConnectTimeout=10", alias])
            return result.returncode

        returncode = suspend_curses_and_run(stdscr, do_connect)
        if returncode == 255:
            message_screen(stdscr, [t("connect_error", alias=alias)])
        else:
            message_screen(stdscr, [t("session_ended")])


def main(stdscr):
    curses.curs_set(0)
    load_lang()
    while True:
        choice = menu(stdscr, t("title"), [
            t("opt_add"),
            t("opt_list"),
            t("opt_lang", name=LANG_NAMES[_current_lang]),
            t("opt_quit"),
        ])
        if choice is None or choice == 3:
            return
        elif choice == 0:
            screen_add_host(stdscr)
        elif choice == 1:
            screen_list_hosts(stdscr)
        elif choice == 2:
            other_lang = "ja" if _current_lang == "en" else "en"
            save_lang(other_lang)


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        sys.exit(0)
