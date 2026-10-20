import random

import pytest

from sagynysh import markov

VOCAB_MESSAGES = [
    "кот сидит дома",
    "кот спит тихо",
    "собака бежит быстро",
    "собака лает громко",
]


async def _learn_corpus(conn, chat_id, messages, order, times=1):
    for _ in range(times):
        for message in messages:
            await markov.learn(conn, chat_id, message, order)


async def test_generate_returns_none_below_threshold(conn):
    # 4 messages * 2 = 8 learned, below MIN_MESSAGES_LEARNED (20)
    await _learn_corpus(conn, chat_id=1, messages=VOCAB_MESSAGES, order=1, times=2)

    result = await markov.generate(conn, chat_id=1, order=1, max_words=25, rng=random.Random(1))
    assert result is None


async def test_learn_then_generate_only_uses_corpus_words(conn):
    order = 1
    await _learn_corpus(conn, chat_id=1, messages=VOCAB_MESSAGES, order=order, times=6)
    vocab = {word for message in VOCAB_MESSAGES for word in message.split()}

    for seed_value in range(10):
        result = await markov.generate(
            conn, chat_id=1, order=order, max_words=25, rng=random.Random(seed_value)
        )
        assert result is not None
        for word in result.split():
            assert word in vocab


async def test_generate_order_2_only_uses_corpus_words(conn):
    order = 2
    await _learn_corpus(conn, chat_id=1, messages=VOCAB_MESSAGES, order=order, times=6)
    vocab = {word for message in VOCAB_MESSAGES for word in message.split()}

    for seed_value in range(10):
        result = await markov.generate(
            conn, chat_id=1, order=order, max_words=25, rng=random.Random(seed_value)
        )
        assert result is not None
        for word in result.split():
            assert word in vocab


async def test_seeded_generation_starts_from_seed_when_at_start(conn):
    order = 1
    await _learn_corpus(conn, chat_id=1, messages=VOCAB_MESSAGES, order=order, times=6)

    result = await markov.generate(
        conn, chat_id=1, order=order, max_words=25, seed="собака", rng=random.Random(3)
    )
    assert result is not None
    assert result.split()[0] == "собака"


async def test_seeded_generation_uses_fallback_when_seed_is_mid_sequence(conn):
    order = 1
    await _learn_corpus(conn, chat_id=1, messages=VOCAB_MESSAGES, order=order, times=6)

    # "тихо" only ever appears as the last word of a message, never first
    result = await markov.generate(
        conn, chat_id=1, order=order, max_words=25, seed="тихо", rng=random.Random(2)
    )
    assert result is not None
    assert result.split()[0] == "тихо"


async def test_seeded_generation_falls_back_silently_when_seed_unknown(conn):
    order = 1
    await _learn_corpus(conn, chat_id=1, messages=VOCAB_MESSAGES, order=order, times=6)

    result = await markov.generate(
        conn, chat_id=1, order=order, max_words=25, seed="неизвестное", rng=random.Random(5)
    )
    assert result is not None


async def test_anti_parrot_returns_the_only_learned_message_after_retries(conn):
    order = 1
    message = "привет как дела"
    for _ in range(20):
        await markov.learn(conn, chat_id=1, text=message, order=order)

    result = await markov.generate(conn, chat_id=1, order=order, max_words=25, rng=random.Random(7))
    assert result == message


def test_pick_seed_chooses_a_token_of_at_least_four_chars():
    rng = random.Random(0)
    seed = markov.pick_seed("э я и кот бегает быстро", rng)
    assert seed is not None
    assert len(seed) >= 4


def test_pick_seed_returns_none_when_no_long_tokens():
    rng = random.Random(0)
    assert markov.pick_seed("э я и", rng) is None


@pytest.mark.parametrize("learned_order,requested_order", [(5, 1), (5, 2), (1, 5), (2, 5)])
@pytest.mark.parametrize("seed", [None, "кот", "тихо"])
async def test_order_changes_preserve_usable_memory(conn, learned_order, requested_order, seed):
    await _learn_corpus(conn, 1, VOCAB_MESSAGES, learned_order, times=6)
    vocab = {word for message in VOCAB_MESSAGES for word in message.split()}
    for i in range(3):
        result = await markov.generate(
            conn, 1, requested_order, 25, seed=seed, rng=random.Random(i)
        )
        assert result
        assert set(result.split()) <= vocab
        if seed:
            assert result.split()[0] == seed


async def test_learning_after_order_change_keeps_both_histories(conn):
    await _learn_corpus(conn, 1, ["кот сидит дома"], 5, times=20)
    await _learn_corpus(conn, 1, ["пёс сидит снаружи"], 1, times=20)
    for order in (1, 5):
        for seed in ("кот", "пёс"):
            result = await markov.generate(conn, 1, order, 25, seed=seed)
            assert result and result.split()[0] == seed
