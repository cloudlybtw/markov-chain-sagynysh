# Sagynysh (Сагыныш)

A local, self-hosted recreation of the "Сглыпа" Telegram bot for a private friend group.

It reads every message in the group chats it's added to, learns from them with a
word-level Markov chain (kept separately per chat), and occasionally replies with
absurd sentences remixed from the group's own words. It also remembers photos
posted in the chat and can turn them into demotivators and memes with generated
captions.

Coherence is not the goal — the humor comes from the chat's own vocabulary said
back to it in ways nobody actually said it.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended), or `pip` as a fallback
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Setup

### 1. Create the bot

1. Message [@BotFather](https://t.me/BotFather) and run `/newbot`, following the prompts.
2. Copy the token it gives you — you'll need it for `.env` below.
3. **Disable privacy mode**: `/setprivacy` → select your bot → **Disable**.
   Without this, the bot only sees messages that are commands or replies to it,
   and will never learn from normal chat. If you change this *after* already
   adding the bot to a group, **remove it from the group and add it back** —
   privacy mode only takes effect on (re-)join.
4. Optional but recommended for a private bot: `/setjoingroups` → **Disable**
   once you've added it to your group, so nobody else can add it elsewhere.

### 2. Install and configure

```bash
git clone git@github.com:cloudlybtw/markov-chain-sagynysh.git
cd markov-chain-sagynysh
uv sync
cp .env.example .env
```

Edit `.env` and set at least `BOT_TOKEN`:

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | *(required)* | Token from @BotFather |
| `DB_PATH` | `data/sagynysh.db` | SQLite file location |
| `COMMON_REPLY_CHANCE` | `10` | Default % chance of responding to ordinary messages; legacy `DEFAULT_CHANCE` is accepted when this is absent |
| `DIRECT_REPLY_CHANCE` | same as common default | Default % chance of responding to a reply to the bot |
| `MEME_CHANCE` | `5` | Percentage of random replies that become memes, when photos are available |
| `DEMOTIVATOR_CHANCE` | `5` | Percentage of random replies that become demotivators; combined with `MEME_CHANCE`, at most 100 |
| `MARKOV_ORDER` | `1` | Chain order, 1–5 — `1` is chaotic/funny; higher orders use more context |
| `MAX_WORDS` | `25` | Hard cap on generated message length |
| `ALLOWED_CHAT_IDS` | *(empty)* | Comma-separated chat ID whitelist. Empty = any chat may use the bot; if set, the bot silently leaves any other group it's added to |
| `ADMIN_USER_IDS` | *(empty)* | Additional bot admins. Telegram group owners/admins automatically have access in their own group; empty never grants access to ordinary members |

`.env` supplies the initial settings for each chat. Commands save per-chat settings
in SQLite and take effect immediately, surviving restarts and `/forget`. Editing
`.env` changes defaults for chats whose settings have not been initialized yet;
use the commands to change an existing chat. Existing reply chances and learned
history are preserved automatically when upgrading.

### 3. Run it

```bash
uv run python -m sagynysh
```

Add the bot to your group chat. It starts with no data — see below for a
faster way to warm it up than waiting for organic chat.

If `uv` isn't available, fall back to plain `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m sagynysh
```

## Pre-training from a chat export

The bot is funny fastest if you seed it with your group's existing history
instead of waiting for it to relearn everything from scratch.

1. In Telegram Desktop: chat menu → **Export chat history**.
2. Export as **HTML** or **Machine-readable JSON**, whichever is available.
   Text-only content is enough; you don't need to export media.
3. Run:

   ```bash
   uv run python -m sagynysh.tools.train_from_export result.json --chat-id -1001234567890
   ```

   For the HTML export in this repository, pass the whole folder so every page
   (`messages.html`, `messages2.html`, etc.) is imported:

   ```bash
   uv run python -m sagynysh.tools.train_from_export ChatExport_DevGng --chat-id -1001234567890
   ```

   A single HTML file is also accepted, but imports only that page. No conversion
   to JSON is needed. HTML export folders named `ChatExport*` are gitignored to
   keep private chat history out of commits.

   Replace the example chat ID with the actual numeric Bot API ID of the group
   where the bot will run: start the bot and send `/stats` in that group to see
   its ID. The HTML export's message IDs are not chat IDs.
   The trainer defaults to `--order 1 --db-path data/sagynysh.db`; pass these flags
   explicitly if your bot uses different values. It does not read `.env`.

Service messages (joins, pins, calls, ...), forwards, and commands are skipped
automatically — only genuine chat messages get learned.
Captions are included; exported photos are not imported, since local files do
not contain the Bot API `file_id`s needed by the bot. Bot authorship cannot be
reliably detected in exports. Run an import only once: repeating it increases
the learned counts again.

To try DevGng's history in a separate group containing just you and the bot:

1. Configure `.env` with your token, `DB_PATH=data/sagynysh.db`, and `MARKOV_ORDER=1`.
   Initially leave `ALLOWED_CHAT_IDS` empty, or include the test group's ID if you
   already know it.
2. Start with `uv run python -m sagynysh`, then send `/stats` in the test group.
   Copy the `ID чата` value, including the minus sign.
3. Stop the bot with Ctrl+C. Run the HTML import command above once, using that ID.
4. Start the bot again. `/stats` should show at least 10,365 learned messages.
   Send `/say` repeatedly to sample the generated replies.
5. For automatic replies, send `/chance 100` and then normal messages. Random
   replies have a 10-second cooldown. Replies to the bot use `/direct_chance`
   and are sent as threaded replies. Explicit mentions by `@username`
   or the name Сглыпа/Sagynysh always trigger a response when enough data is available.
   Privacy mode must be disabled
   as described in Setup for it to see normal group messages.

Training the test group leaves other groups' histories unchanged. If your bot
uses a different database path or Markov order, pass matching `--db-path` and
`--order` flags to the trainer.

## Commands

| Command | Behavior |
|---|---|
| `/start`, `/help` | What the bot does, works in DMs too |
| `/admin_only [on\|off]` | Admin-only: show/set whether every command in this group requires admin rights; default `off` |
| `/chance [N]` | Admin-only: show/set response chance for ordinary messages (0–100); aliases `/common_chance`, `/common_reply_chance` |
| `/direct_chance [N]` | Admin-only: show/set response chance for replies to the bot (0–100); alias `/direct_reply_chance` |
| `/markov_order [N]` | Admin-only: show/set Markov order (1–5) for learning, replies, `/say`, and image captions |
| `/meme_chance [N]` | Admin-only: show/set the percentage of random replies that become memes (0–100) |
| `/demotivator_chance [N]` | Admin-only: show/set the percentage of random replies that become demotivators (0–100) |
| `/say` | Generate a message right now |
| `/demotivator` | Demotivator from a random saved photo (or the one you're replying to) |
| `/meme` | Same, as a top/bottom-text meme |
| `/stats` | Messages learned, unique transitions, photos saved, for this chat |
| `/forget` | Wipe this chat's learned data and saved photos, with a confirm button |

All settings commands, including `/admin_only`, require admin rights even when showing a value.
The bot checks the current group's administrator list through
[`getChatAdministrators`](https://core.telegram.org/bots/api#getchatadministrators)
on each admin command, so promotions/demotions apply automatically. Group admins
do not gain access in other groups. Anonymous group admins may use commands too;
the `/forget` confirmation button requires an identifiable current admin or a
configured bot admin. `/forget` is also admin-only, with rights checked again at
confirmation. If the administrator lookup fails, access is denied; configured
`ADMIN_USER_IDS` still work.

`/admin_only on` restricts every bot command in that group to current group admins
and configured bot admins, including `/start`, `/help`, `/stats`, and all command
aliases. `/admin_only off` restores public access to `/say`, `/meme`,
`/demotivator`, and the informational commands. Settings and `/forget` remain
admin-only in both modes. With no argument, `/admin_only` shows the current mode.
Only `on` and `off` are accepted (case-insensitive). The mode is separate for each
chat, defaults to `off` for existing and new chats, and survives restarts and
`/forget`. Automatic replies, replies to the bot, mentions, and their probabilities
are unchanged. Private chats still only provide `/start` and `/help`; group command
restrictions do not apply to that private help.

For example, `/chance 10`, `/direct_chance 80`, `/meme_chance 20`, and
`/demotivator_chance 10` mean a 10% chance of responding to an ordinary message,
an 80% chance of responding to a reply to the bot, and a random-response mix of
20% memes, 10% demotivators, and 70% text. Media shares must sum to at most 100.
Without photos, the bot sends text instead. The bot waits for at least 20 learned
messages before automatic replies, including images. Explicit mentions always
produce threaded text replies when enough data is available, regardless of chances.
Manual `/meme` and `/demotivator` commands are unaffected by these probabilities.

Changing order never wipes memory. Generation combines counts from longer contexts
when requesting a lower order, and falls back to shorter contexts when requesting
a higher order without enough matching history. New messages are learned with the
chat's selected order; older data cannot recover context it never recorded.

## Privacy

- The bot stores the text of messages sent in groups it's in, in order to learn
  from them — `/help` says so, and `/forget` always works to wipe a chat's data.
- It never learns from or responds to anything in a DM except `/start`/`/help`.
- Message contents are never logged; only counts and chat/user IDs are.
- Only Telegram `file_id`s are stored for photos, never image bytes.

## Development

```bash
uv sync                  # installs dev dependencies too
uv run pytest            # run the test suite
uv run ruff check .      # lint
uv run ruff format .     # format
```

## Deployment

Two options are included for running this on a small VPS or a Raspberry Pi;
pick whichever fits. Both expect `.env` to already exist (see Setup above).

### Option A: systemd

```bash
sudo useradd --system --create-home --home-dir /opt/sagynysh sagynysh
sudo -u sagynysh git clone git@github.com:cloudlybtw/markov-chain-sagynysh.git /opt/sagynysh
cd /opt/sagynysh
sudo -u sagynysh cp .env.example .env   # then edit it with BOT_TOKEN etc.
sudo -u sagynysh uv sync --frozen --no-dev   # creates /opt/sagynysh/.venv

sudo cp deploy/sagynysh.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sagynysh
journalctl -u sagynysh -f   # logs
```

[`deploy/sagynysh.service`](deploy/sagynysh.service) assumes the paths above
(`/opt/sagynysh`, user `sagynysh`) — edit it first if yours differ.

### Option B: Docker

```bash
docker compose up -d --build
docker compose logs -f
```

This builds the image from the included `Dockerfile`, mounts `./data` for the
SQLite file so it survives container rebuilds, and reads `.env` for config.
