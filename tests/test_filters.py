from sagynysh import filters


def test_accepts_normal_message():
    assert filters.should_learn("привет, как дела сегодня?", is_bot=False, is_forwarded=False)


def test_rejects_bot_messages():
    assert not filters.should_learn("привет всем", is_bot=True, is_forwarded=False)


def test_rejects_forwarded_messages():
    assert not filters.should_learn("привет всем", is_bot=False, is_forwarded=True)


def test_rejects_commands():
    assert not filters.should_learn("/start", is_bot=False, is_forwarded=False)
    assert not filters.should_learn("/say сгенерируй что-нибудь", is_bot=False, is_forwarded=False)


def test_rejects_link_only_messages():
    assert not filters.should_learn("https://example.com/path", is_bot=False, is_forwarded=False)
    assert not filters.should_learn("https://a.com www.b.com", is_bot=False, is_forwarded=False)


def test_accepts_message_with_link_and_text():
    assert filters.should_learn(
        "смотри https://example.com/path вот это", is_bot=False, is_forwarded=False
    )


def test_rejects_empty_or_whitespace_only():
    assert not filters.should_learn("", is_bot=False, is_forwarded=False)
    assert not filters.should_learn("   ", is_bot=False, is_forwarded=False)


def test_rejects_messages_over_max_tokens():
    text = " ".join(["слово"] * 61)
    assert not filters.should_learn(text, is_bot=False, is_forwarded=False)


def test_accepts_messages_up_to_max_tokens():
    text = " ".join(["слово"] * 60)
    assert filters.should_learn(text, is_bot=False, is_forwarded=False)


def test_rejects_message_that_is_only_a_self_mention():
    assert not filters.should_learn(
        "@sagynysh", is_bot=False, is_forwarded=False, bot_username="sagynysh"
    )
