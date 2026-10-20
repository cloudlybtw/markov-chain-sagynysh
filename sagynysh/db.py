"""Schema, connection setup, and all SQL for Sagynysh."""

from __future__ import annotations

import aiosqlite

from sagynysh.config import MAX_MARKOV_ORDER, ChatSettings, Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    chance      INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transitions (
    chat_id  INTEGER NOT NULL,
    prev     TEXT    NOT NULL,
    next     TEXT    NOT NULL,
    count    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (chat_id, prev, next)
);
CREATE INDEX IF NOT EXISTS idx_trans_lookup ON transitions(chat_id, prev);

CREATE TABLE IF NOT EXISTS photos (
    chat_id   INTEGER NOT NULL,
    file_id   TEXT    NOT NULL,
    added_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (chat_id, file_id)
);

CREATE TABLE IF NOT EXISTS stats (
    chat_id          INTEGER PRIMARY KEY,
    messages_learned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id INTEGER PRIMARY KEY,
    markov_order INTEGER NOT NULL CHECK (markov_order BETWEEN 1 AND 5),
    direct_reply_chance INTEGER NOT NULL CHECK (direct_reply_chance BETWEEN 0 AND 100),
    meme_chance INTEGER NOT NULL CHECK (meme_chance BETWEEN 0 AND 100),
    demotivator_chance INTEGER NOT NULL CHECK (demotivator_chance BETWEEN 0 AND 100),
    CHECK (meme_chance + demotivator_chance <= 100)
);

CREATE TABLE IF NOT EXISTS command_access (
    chat_id INTEGER PRIMARY KEY,
    admin_only INTEGER NOT NULL DEFAULT 0 CHECK (admin_only IN (0, 1))
);
"""


async def connect(db_path: str) -> aiosqlite.Connection:
    """Open a connection and ensure the schema exists."""
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    return conn


async def get_or_create_chat(conn: aiosqlite.Connection, chat_id: int, default_chance: int) -> int:
    """Return the chat's reply chance, creating the chat row if it's new."""
    await conn.execute(
        "INSERT INTO chats (chat_id, chance) VALUES (?, ?) ON CONFLICT(chat_id) DO NOTHING",
        (chat_id, default_chance),
    )
    await conn.commit()
    cursor = await conn.execute("SELECT chance FROM chats WHERE chat_id = ?", (chat_id,))
    row = await cursor.fetchone()
    return row["chance"]


async def set_chance(conn: aiosqlite.Connection, chat_id: int, chance: int) -> None:
    await conn.execute("UPDATE chats SET chance = ? WHERE chat_id = ?", (chance, chat_id))
    await conn.commit()


async def get_admin_only(conn: aiosqlite.Connection, chat_id: int) -> bool:
    """Existing and new chats allow public commands until an admin opts in."""
    cursor = await conn.execute(
        "SELECT admin_only FROM command_access WHERE chat_id = ?", (chat_id,)
    )
    row = await cursor.fetchone()
    return bool(row["admin_only"]) if row is not None else False


async def set_admin_only(conn: aiosqlite.Connection, chat_id: int, enabled: bool) -> None:
    await conn.execute(
        """INSERT INTO command_access (chat_id, admin_only) VALUES (?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET admin_only = excluded.admin_only""",
        (chat_id, int(enabled)),
    )
    await conn.commit()


async def get_chat_settings(
    conn: aiosqlite.Connection, chat_id: int, config: Config
) -> ChatSettings:
    cursor = await conn.execute(
        "SELECT c.chance, s.* FROM chats c JOIN chat_settings s USING(chat_id) WHERE chat_id = ?",
        (chat_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        await get_or_create_chat(conn, chat_id, config.default_chance)
        await conn.execute(
            """INSERT INTO chat_settings
               (chat_id, markov_order, direct_reply_chance, meme_chance, demotivator_chance)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
            (
                chat_id,
                config.markov_order,
                config.direct_reply_chance,
                config.meme_chance,
                config.demotivator_chance,
            ),
        )
        await conn.commit()
        return await get_chat_settings(conn, chat_id, config)
    return ChatSettings(
        markov_order=row["markov_order"],
        common_reply_chance=row["chance"],
        direct_reply_chance=row["direct_reply_chance"],
        meme_chance=row["meme_chance"],
        demotivator_chance=row["demotivator_chance"],
    )


async def set_chat_setting(
    conn: aiosqlite.Connection, chat_id: int, config: Config, name: str, value: int
) -> None:
    """Persist one override; media shares are checked atomically against the other share."""
    columns = {"markov_order", "direct_reply_chance", "meme_chance", "demotivator_chance"}
    if name not in columns | {"common_reply_chance"}:
        raise ValueError("Unknown chat setting")
    low, high = (1, MAX_MARKOV_ORDER) if name == "markov_order" else (0, 100)
    if not low <= value <= high:
        raise ValueError("Setting out of range")
    await get_chat_settings(conn, chat_id, config)
    if name == "common_reply_chance":
        await set_chance(conn, chat_id, value)
        return
    # Column names come only from the fixed allowlist above, never user input.
    condition = ""
    params: tuple[int, ...] = (value, chat_id)
    if name in {"meme_chance", "demotivator_chance"}:
        other = "demotivator_chance" if name == "meme_chance" else "meme_chance"
        condition = f" AND ? + COALESCE({other}, ?) <= 100"
        params += (value, getattr(config, other))
    cursor = await conn.execute(
        f"UPDATE chat_settings SET {name} = ? WHERE chat_id = ?{condition}", params
    )
    await conn.commit()
    if cursor.rowcount != 1:
        raise ValueError("Media chances must not exceed 100 in total")


async def get_generation_transitions(
    conn: aiosqlite.Connection, chat_id: int, prev: str
) -> list[tuple[str, int]]:
    """Project longer learned contexts onto a suffix, preserving their weights.

    Each learned message has one order, so each transition contributes once.
    This lets order changes reuse old memory without reconstructing messages.
    """
    suffix = "\x1f" + prev
    cursor = await conn.execute(
        """SELECT next, SUM(count) AS weight FROM transitions
           WHERE chat_id = ? AND (prev = ? OR substr(prev, -length(?)) = ?)
           GROUP BY next ORDER BY next""",
        (chat_id, prev, suffix, suffix),
    )
    return [(row["next"], row["weight"]) for row in await cursor.fetchall()]


async def upsert_transition(
    conn: aiosqlite.Connection, chat_id: int, prev: str, next_: str
) -> None:
    """Record one learned transition. Does not commit — callers batch a whole
    message's transitions into a single transaction."""
    await conn.execute(
        """
        INSERT INTO transitions (chat_id, prev, next, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id, prev, next) DO UPDATE SET count = count + 1
        """,
        (chat_id, prev, next_),
    )


async def get_transitions(
    conn: aiosqlite.Connection, chat_id: int, prev: str
) -> list[tuple[str, int]]:
    cursor = await conn.execute(
        "SELECT next, count FROM transitions WHERE chat_id = ? AND prev = ?",
        (chat_id, prev),
    )
    rows = await cursor.fetchall()
    return [(row["next"], row["count"]) for row in rows]


async def find_prev_for_next(
    conn: aiosqlite.Connection, chat_id: int, next_: str
) -> list[tuple[str, int]]:
    """All (prev, count) pairs that produced `next_`, for fallback seeding."""
    cursor = await conn.execute(
        "SELECT prev, count FROM transitions WHERE chat_id = ? AND next = ?",
        (chat_id, next_),
    )
    rows = await cursor.fetchall()
    return [(row["prev"], row["count"]) for row in rows]


async def increment_messages_learned(conn: aiosqlite.Connection, chat_id: int) -> None:
    """Bump the learned-message counter. Does not commit — see upsert_transition."""
    await conn.execute(
        """
        INSERT INTO stats (chat_id, messages_learned) VALUES (?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET messages_learned = messages_learned + 1
        """,
        (chat_id,),
    )


async def get_stats(conn: aiosqlite.Connection, chat_id: int) -> dict[str, int]:
    cursor = await conn.execute("SELECT messages_learned FROM stats WHERE chat_id = ?", (chat_id,))
    row = await cursor.fetchone()
    messages_learned = row["messages_learned"] if row else 0

    cursor = await conn.execute(
        "SELECT COUNT(*) AS n FROM transitions WHERE chat_id = ?", (chat_id,)
    )
    unique_transitions = (await cursor.fetchone())["n"]

    cursor = await conn.execute("SELECT COUNT(*) AS n FROM photos WHERE chat_id = ?", (chat_id,))
    photos = (await cursor.fetchone())["n"]

    return {
        "messages_learned": messages_learned,
        "unique_transitions": unique_transitions,
        "photos": photos,
    }


async def add_photo(conn: aiosqlite.Connection, chat_id: int, file_id: str) -> None:
    await conn.execute(
        "INSERT INTO photos (chat_id, file_id) VALUES (?, ?) "
        "ON CONFLICT(chat_id, file_id) DO NOTHING",
        (chat_id, file_id),
    )
    await conn.commit()


async def random_photo(conn: aiosqlite.Connection, chat_id: int) -> str | None:
    cursor = await conn.execute(
        "SELECT file_id FROM photos WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1",
        (chat_id,),
    )
    row = await cursor.fetchone()
    return row["file_id"] if row else None


async def forget_chat(conn: aiosqlite.Connection, chat_id: int) -> None:
    """Wipe a chat's transitions, photos and stats. Leaves other chats untouched."""
    await conn.execute("DELETE FROM transitions WHERE chat_id = ?", (chat_id,))
    await conn.execute("DELETE FROM photos WHERE chat_id = ?", (chat_id,))
    await conn.execute("DELETE FROM stats WHERE chat_id = ?", (chat_id,))
    await conn.commit()
