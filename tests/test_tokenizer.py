from sagynysh import tokenizer


def test_punctuation_stays_attached():
    tokens = tokenizer.tokenize("привет, как дела?")
    assert tokens == ["привет,", "как", "дела?"]


def test_casing_is_preserved():
    tokens = tokenizer.tokenize("Привет МИР")
    assert tokens == ["Привет", "МИР"]


def test_urls_are_dropped():
    assert tokenizer.tokenize("смотри https://example.com/path вот") == ["смотри", "вот"]
    assert tokenizer.tokenize("зайди на www.example.com сейчас") == ["зайди", "на", "сейчас"]


def test_self_mentions_are_dropped_case_insensitive():
    tokens = tokenizer.tokenize("эй @Sagynysh расскажи анекдот", bot_username="sagynysh")
    assert tokens == ["эй", "расскажи", "анекдот"]


def test_self_mentions_with_trailing_punctuation_are_dropped():
    tokens = tokenizer.tokenize("@sagynysh, привет!", bot_username="sagynysh")
    assert tokens == ["привет!"]


def test_other_mentions_are_kept():
    tokens = tokenizer.tokenize("привет @friend как дела", bot_username="sagynysh")
    assert tokens == ["привет", "@friend", "как", "дела"]


def test_long_tokens_are_dropped_short_ones_kept():
    long_token = "а" * 41
    short_token = "а" * 40
    tokens = tokenizer.tokenize(f"это {long_token} и {short_token} слова")
    assert long_token not in tokens
    assert short_token in tokens


def test_detokenize_joins_with_single_spaces():
    assert tokenizer.detokenize(["привет", "мир"]) == "привет мир"


def test_build_sequence_pads_start_for_order_1():
    seq = tokenizer.build_sequence(["a", "b"], order=1)
    assert seq == ["__START__", "a", "b", "__END__"]


def test_build_sequence_pads_start_for_order_2():
    seq = tokenizer.build_sequence(["a", "b"], order=2)
    assert seq == ["__START__", "__START__", "a", "b", "__END__"]


def test_build_sequence_handles_empty_tokens():
    seq = tokenizer.build_sequence([], order=2)
    assert seq == ["__START__", "__START__", "__END__"]


def test_cap_words_truncates_to_limit():
    assert tokenizer.cap_words("а б в г д", 3) == "а б в"


def test_cap_words_leaves_short_text_untouched():
    assert tokenizer.cap_words("а б", 8) == "а б"


def test_cap_words_handles_empty_text():
    assert tokenizer.cap_words("", 8) == ""
