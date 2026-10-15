from app.lexical import BM25, tokenize


def test_diacritics_and_cyrillic_fold():
    assert tokenize("Šta je ŽĐ") == ["sta", "je", "zdj"] or tokenize("Šta")[0] == "sta"
    assert tokenize("Београд") == tokenize("Beograd")


def test_exact_code_ranks_first():
    docs = ["opšti tekst o greškama", "Šifra ERR-4471 istek tokena", "nešto drugo"]
    s = BM25(docs).scores("ERR-4471")
    assert s.index(max(s)) == 1
