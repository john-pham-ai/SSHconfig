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

Each alias gets its own known_hosts.d/<alias> file (rather than sharing the
global ~/.ssh/known_hosts), so two aliases pointing at the same address (e.g.
two vehicles reusing an IP) never collide over a cached host fingerprint.
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
KNOWN_HOSTS_DIR = os.path.join(SSH_DIR, "known_hosts.d")


def known_hosts_path(alias):
    return os.path.join(KNOWN_HOSTS_DIR, alias)


LANG_CONFIG_PATH = os.path.expanduser("~/.config/sshtui/lang")
LANG_NAMES = {"en": "English", "ja": "日本語"}

STRINGS = {
    "en": {
        "title": "SSH Config Manager",
        "opt_add": "Add new SSH connection",
        "opt_list": "List / connect to aliases",
        "opt_edit": "Edit an alias",
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
        "hostkey_changed_1": "Host key CHANGED for alias '{alias}' ({hostname}).",
        "hostkey_changed_2": "A different machine now appears to be answering at this address.",
        "hostkey_unknown_1": "Host key for alias '{alias}' ({hostname}) is not yet trusted.",
        "hostkey_fix_footer": "Press 'y' to trust the new key and retry, any other key to cancel",
        "hostkey_trusted": "Key for '{alias}' trusted. Connecting...",
        "hostkey_fix_failed": "Could not automatically fix it:",
        "edit_title": "Edit alias (Enter to select)",
        "edit_prompt_alias": "Alias name",
        "edit_prompt_host": "Address/host",
        "edit_prompt_user": "User",
        "edit_prompt_port": "Port",
        "edit_current_none": "(none)",
        "edit_hint": "{prompt} [current: {current}, blank = keep]:",
        "edit_alias_conflict": "Alias '{alias}' already exists. No changes made.",
        "edit_failed": "Failed to update: {error}",
        "edit_success1": "Updated alias '{old}' -> '{new}'.",
        "edit_success2": "Connect any time with:  ssh {alias}",
    },
    "ja": {
        "title": "SSH 設定マネージャー",
        "opt_add": "新しい SSH 接続を追加",
        "opt_list": "エイリアス一覧 / 接続",
        "opt_edit": "エイリアスを編集",
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
        "hostkey_changed_1": "エイリアス '{alias}' ({hostname}) のホストキーが変更されました。",
        "hostkey_changed_2": "このアドレスには別のマシンが応答しているようです。",
        "hostkey_unknown_1": "エイリアス '{alias}' ({hostname}) のホストキーはまだ信頼されていません。",
        "hostkey_fix_footer": "'y' を押すと新しい鍵を信頼して再試行します。それ以外のキーでキャンセルします。",
        "hostkey_trusted": "'{alias}' の鍵を信頼しました。接続中...",
        "hostkey_fix_failed": "自動的に修正できませんでした:",
        "edit_title": "エイリアスを編集 (Enter で選択)",
        "edit_prompt_alias": "エイリアス名",
        "edit_prompt_host": "アドレス/ホスト",
        "edit_prompt_user": "ユーザー",
        "edit_prompt_port": "ポート",
        "edit_current_none": "(なし)",
        "edit_hint": "{prompt} [現在: {current}, 空欄で変更なし]:",
        "edit_alias_conflict": "エイリアス '{alias}' は既に存在します。変更は行われませんでした。",
        "edit_failed": "更新に失敗しました: {error}",
        "edit_success1": "エイリアス '{old}' を '{new}' に更新しました。",
        "edit_success2": "ssh {alias} でいつでも接続できます。",
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


def _host_block_lines(alias, hostname, user, port):
    lines = [f"Host {alias}\n", f"    HostName {hostname}\n"]
    if user:
        lines.append(f"    User {user}\n")
    if port:
        lines.append(f"    Port {port}\n")
    lines.append(f"    IdentityFile {KEY_PATH}\n")
    lines.append("    IdentitiesOnly yes\n")
    lines.append(f"    UserKnownHostsFile {known_hosts_path(alias)}\n")
    return lines


def append_host_entry(alias, hostname, user, port):
    ensure_ssh_dir()
    os.makedirs(KNOWN_HOSTS_DIR, mode=0o700, exist_ok=True)
    block = "".join(_host_block_lines(alias, hostname, user, port))

    is_new = not os.path.exists(CONFIG_PATH)
    with open(CONFIG_PATH, "a") as f:
        if not is_new:
            f.write("\n")
        f.write(block)
    os.chmod(CONFIG_PATH, 0o600)


def rewrite_host_entry(old_alias, new_alias, hostname, user, port):
    os.makedirs(KNOWN_HOSTS_DIR, mode=0o700, exist_ok=True)
    with open(CONFIG_PATH) as f:
        lines = f.readlines()

    start, end = find_host_block(lines, old_alias)
    if start is None:
        raise ValueError(f"Alias '{old_alias}' not found in {CONFIG_PATH}")

    lines[start:end] = _host_block_lines(new_alias, hostname, user, port)
    with open(CONFIG_PATH, "w") as f:
        f.writelines(lines)
    os.chmod(CONFIG_PATH, 0o600)

    old_kh_path = known_hosts_path(old_alias)
    new_kh_path = known_hosts_path(new_alias)
    if new_alias != old_alias and os.path.exists(old_kh_path) and not os.path.exists(new_kh_path):
        os.rename(old_kh_path, new_kh_path)


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
        "-o", "ConnectTimeout=10",
        "-o", f"UserKnownHostsFile={known_hosts_path(alias)}",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if port:
        cmd += ["-p", port]
    cmd.append(target)
    # Inherits the real terminal so ssh-copy-id can prompt for the password itself.
    result = subprocess.run(cmd)
    return result.returncode


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

    changed = "IDENTIFICATION HAS CHANGED" in output.upper()
    unknown = (not changed) and ("Host key verification failed" in output or "no matching host key" in output.lower())

    if not (changed or unknown):
        # Some other failure (auth, network, etc) -- not a key issue, let the
        # real ssh attempt show its own error naturally.
        return True

    detail_lines = [l for l in output.strip().splitlines() if l.strip()][-6:]
    if changed:
        header = [t("hostkey_changed_1", alias=alias, hostname=hostname), t("hostkey_changed_2"), ""]
    else:
        header = [t("hostkey_unknown_1", alias=alias, hostname=hostname), ""]
    stdscr.erase()
    for i, line in enumerate(header + detail_lines):
        safe_addstr(stdscr, i, 2, line)
    h, _ = stdscr.getmaxyx()
    safe_addstr(stdscr, h - 1, 2, t("hostkey_fix_footer"), curses.A_DIM)
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
        message_screen(stdscr, [t("hostkey_trusted", alias=alias)], wait_key=False)
    else:
        message_screen(stdscr, [t("hostkey_fix_failed")] + output2.strip().splitlines()[-6:])
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
        return run_ssh_copy_id(alias, user, hostname, port)

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
        hostname = chosen["hostname"]

        if not ensure_host_trust(stdscr, alias, hostname):
            continue

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


def screen_edit_host(stdscr):
    hosts = read_hosts()
    if not hosts:
        message_screen(stdscr, [t("no_aliases"), t("add_one_first")])
        return

    chosen = search_menu(stdscr, t("edit_title"), hosts, _host_display)
    if chosen is None:
        return

    def with_default(prompt_key, current):
        current_label = current if current else t("edit_current_none")
        value = text_input(stdscr, t("edit_hint", prompt=t(prompt_key), current=current_label))
        return value if value else current

    new_alias = with_default("edit_prompt_alias", chosen["alias"])
    if new_alias != chosen["alias"] and alias_exists(new_alias):
        message_screen(stdscr, [t("edit_alias_conflict", alias=new_alias)])
        return

    new_hostname = with_default("edit_prompt_host", chosen["hostname"])
    new_user = with_default("edit_prompt_user", chosen["user"])
    new_port = with_default("edit_prompt_port", chosen["port"])

    try:
        rewrite_host_entry(chosen["alias"], new_alias, new_hostname, new_user, new_port)
    except ValueError as e:
        message_screen(stdscr, [t("edit_failed", error=e)])
        return

    message_screen(stdscr, [
        t("edit_success1", old=chosen["alias"], new=new_alias),
        t("edit_success2", alias=new_alias),
    ])


def main(stdscr):
    curses.curs_set(0)
    load_lang()
    while True:
        choice = menu(stdscr, t("title"), [
            t("opt_add"),
            t("opt_list"),
            t("opt_edit"),
            t("opt_lang", name=LANG_NAMES[_current_lang]),
            t("opt_quit"),
        ])
        if choice is None or choice == 4:
            return
        elif choice == 0:
            screen_add_host(stdscr)
        elif choice == 1:
            screen_list_hosts(stdscr)
        elif choice == 2:
            screen_edit_host(stdscr)
        elif choice == 3:
            other_lang = "ja" if _current_lang == "en" else "en"
            save_lang(other_lang)


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        sys.exit(0)
