# sshtui

A small terminal UI for managing SSH host aliases with key-based (passwordless) auth.

- **Add new SSH connection**: enter an alias + `user@host[:port]`. It reuses (or generates)
  `~/.ssh/id_ed25519` / `.pub`, runs `ssh-copy-id` so you type your password into its own
  normal prompt (sshtui never sees or stores it), then appends a `Host` block to
  `~/.ssh/config` on success.
- **List / connect to aliases**: search-as-you-type over saved `Host` entries in
  `~/.ssh/config`, then Enter to `ssh` in.
- **Edit an alias**: rename an alias or change its host/user/port after the fact.
- **Language**: cycle English / 日本語 / English + 日本語 from the main menu; the choice is
  remembered.

日本語:

- **新しい SSH 接続を追加**: エイリアスと `user@host[:port]` を入力します。`~/.ssh/id_ed25519` /
  `.pub` を再利用（なければ生成）し、`ssh-copy-id` を実行してパスワードはそのプロンプトに直接
  入力します（sshtui がパスワードを読み取ったり保存したりすることはありません）。成功すると
  `~/.ssh/config` に `Host` ブロックが追記されます。
- **エイリアス一覧 / 接続**: `~/.ssh/config` に保存された `Host` エントリをインクリメンタル検索
  し、Enter で `ssh` 接続します。
- **エイリアスを編集**: エイリアス名や host/user/port を後から変更できます。
- **言語**: メインメニューから English / 日本語 / English + 日本語 を順に切り替えられます。選択
  内容は保存されます。

Each alias gets its own `~/.ssh/known_hosts.d/<alias>` file instead of sharing the global
`~/.ssh/known_hosts`, so two aliases pointing at the same address (e.g. two vehicles that
reuse an IP) never collide over a cached host fingerprint. If a saved alias's host key
changes or isn't trusted yet, sshtui detects it before connecting and offers to fix it.

各エイリアスは共有の `~/.ssh/known_hosts` ではなく専用の `~/.ssh/known_hosts.d/<alias>`
ファイルを持つため、同じアドレスを指す 2 つのエイリアス（例: 同じ IP を使い回す 2 台の車両）が
ホストフィンガープリントのキャッシュで衝突することはありません。保存済みエイリアスのホストキー
が変更された、またはまだ信頼されていない場合、sshtui は接続前にそれを検知して修正を提案します。

## Requirements

Only the Python standard library is used (curses, subprocess, etc.) plus the system
`ssh` / `ssh-keygen` / `ssh-copy-id` binaries. To check/install those:

```bash
./build_deps.sh
```

## 必要環境

Python 標準ライブラリ（curses, subprocess など）と、システムの `ssh` / `ssh-keygen` /
`ssh-copy-id` バイナリのみを使用します。これらを確認・インストールするには:

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

## 実行方法

セットアップ後（下記参照）は、次のコマンドを実行するだけです:

```bash
configssh
```

またはエイリアスを使わずに直接実行:

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

## 新しいマシンでの初回セットアップ

```bash
git clone <your-repo-url> ~/SSHconfig   # パスはどこでも構いません
cd ~/SSHconfig
./build_deps.sh                 # ssh 関連ツールの確認・インストール
./install.sh                    # このリポジトリの場所に合わせて configssh コマンドを設定
```

`install.sh` は `~/.local/bin/configssh` を作成し、このリポジトリの実際の場所を指すようにしま
す。また `~/.local/bin` がまだ `PATH` に含まれていない場合は警告します。その後はどのターミナル
からでも `configssh` を実行できます。
