from app.chunking import chunk_text


def test_never_exceeds_limit_even_without_blank_lines():
    text = ". ".join(f"Rečenica broj {i} sa nešto sadržaja" for i in range(120))
    assert all(len(c) <= 600 for c in chunk_text(text))


def test_splits_runaway_token_run():
    assert all(len(c) <= 200 for c in chunk_text("x" * 1000, max_chars=200))


def test_short_text_is_single_chunk():
    assert chunk_text("Kratak tekst.") == ["Kratak tekst."]


def test_overlap_carries_context():
    text = " ".join(f"Rec{i}." for i in range(400))
    cs = chunk_text(text, max_chars=200, overlap=50)
    assert len(cs) > 1 and cs[1].split()[0] in cs[0]
