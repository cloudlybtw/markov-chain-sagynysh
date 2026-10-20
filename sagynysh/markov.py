"""Markov chain learning and generation. Pure logic — the DB connection is
passed in, no Telegram dependency."""

from __future__ import annotations

import random

import aiosqlite

from sagynysh import db, tokenizer

MIN_MESSAGES_LEARNED = 20
ANTI_PARROT_RETRIES = 5


async def learn(
    conn: aiosqlite.Connection,
    chat_id: int,
    text: str,
    order: int,
    bot_username: str | None = None,
) -> None:
    """Learn every transition in `text` for `chat_id`, in one transaction."""
    tokens = tokenizer.tokenize(text, bot_username=bot_username)
    if not tokens:
        return

    sequence = tokenizer.build_sequence(tokens, order)
    for i in range(order, len(sequence)):
        prev = tokenizer.CONTEXT_SEP.join(sequence[i - order : i])
        await db.upsert_transition(conn, chat_id, prev, sequence[i])

    await db.increment_messages_learned(conn, chat_id)
    await conn.commit()


def pick_seed(text: str, rng: random.Random) -> str | None:
    """Pick a random 4+ character token from a triggering message, so replies
    can be loosely on-topic."""
    candidates = [t for t in tokenizer.tokenize(text) if len(t) >= 4]
    return rng.choice(candidates) if candidates else None


async def generate(
    conn: aiosqlite.Connection,
    chat_id: int,
    order: int,
    max_words: int,
    seed: str | None = None,
    rng: random.Random | None = None,
) -> str | None:
    """Generate a message from `chat_id`'s learned transitions, or None if it
    hasn't learned enough yet."""
    rng = rng if rng is not None else random.Random()

    stats = await db.get_stats(conn, chat_id)
    if stats["messages_learned"] < MIN_MESSAGES_LEARNED:
        return None

    tokens: list[str] = []
    for _ in range(ANTI_PARROT_RETRIES):
        tokens, all_forced = await _generate_once(conn, chat_id, order, max_words, seed, rng)
        if not all_forced:
            break

    return tokenizer.detokenize(tokens)


async def _generate_once(
    conn: aiosqlite.Connection,
    chat_id: int,
    order: int,
    max_words: int,
    seed: str | None,
    rng: random.Random,
) -> tuple[list[str], bool]:
    context, tokens = await _seeded_start(conn, chat_id, order, seed, rng)
    all_forced = True

    while len(tokens) < max_words:
        rows = await _context_rows(conn, chat_id, context)
        if not rows:
            break

        if len(rows) > 1:
            all_forced = False
        next_word = _weighted_choice(rows, rng)

        if next_word == tokenizer.END:
            break

        tokens.append(next_word)
        context = [*context[1:], next_word]

    return tokens, all_forced


async def _seeded_start(
    conn: aiosqlite.Connection,
    chat_id: int,
    order: int,
    seed: str | None,
    rng: random.Random,
) -> tuple[list[str], list[str]]:
    """Resolve the starting context and any tokens already emitted (the seed
    word, if one was placed). Falls back to a plain start silently."""
    start_context = [tokenizer.START] * order
    if not seed:
        return start_context, []

    start_rows = await _context_rows(conn, chat_id, start_context)
    if any(next_word == seed for next_word, _ in start_rows):
        return [*start_context[1:], seed], [seed]

    fallback_rows = await db.find_prev_for_next(conn, chat_id, seed)
    if fallback_rows:
        prev = _weighted_choice(fallback_rows, rng)
        context = ([tokenizer.START] * order + prev.split(tokenizer.CONTEXT_SEP))[-order:]
        return [*context[1:], seed], [seed]

    return start_context, []


async def _context_rows(
    conn: aiosqlite.Connection, chat_id: int, context: list[str]
) -> list[tuple[str, int]]:
    for offset in range(len(context)):
        prev = tokenizer.CONTEXT_SEP.join(context[offset:])
        rows = await db.get_generation_transitions(conn, chat_id, prev)
        if rows:
            return rows
    return []


def _weighted_choice(rows: list[tuple[str, int]], rng: random.Random) -> str:
    values = [value for value, _ in rows]
    weights = [count for _, count in rows]
    return rng.choices(values, weights=weights, k=1)[0]
