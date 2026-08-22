from app.services.book_analysis import (
    analyze_text,
    coverage_curve,
    extract_book_text,
    fallback_lemmatize,
    title_from_filename,
)

FOX_STORY = """
The fox ran to the hill. The fox ran to the hill again.
The rabbit sat on the hill. The rabbit sat and the fox ran.
The carrot sat on the hill. The fox ate the carrot. The rabbit ate the carrot.
"""


def test_fallback_lemmatize_folds_inflections() -> None:
    assert fallback_lemmatize("ran") == "run"
    assert fallback_lemmatize("running") == "run"
    assert fallback_lemmatize("foxes") == "fox"
    assert fallback_lemmatize("ate") == "eat"


def test_coverage_curve_zipf() -> None:
    freqs = [("a", 50), ("b", 30), ("c", 10), ("d", 5), ("e", 5)]
    curve = coverage_curve(freqs)
    assert curve["50"] == 1
    assert curve["80"] == 2
    assert curve["90"] >= 3


def test_analyze_text_skips_function_words_and_caps_study_set() -> None:
    analysis = analyze_text(FOX_STORY, coverage_target=0.8)
    lemmas = {item.lemma for item in analysis.lemmas}
    assert "the" not in lemmas
    assert "and" not in lemmas
    assert "fox" in lemmas
    study = {item.lemma for item in analysis.lemmas if item.in_study_set}
    assert "fox" in study
    assert len(study) < analysis.content_lemma_count or analysis.content_lemma_count <= 8
    assert analysis.coverage_curve["80"] >= 1
    assert analysis.token_count > 20


def test_title_and_txt_extract() -> None:
    assert title_from_filename("charlotte-s-web.txt") == "charlotte s web"
    text = extract_book_text(filename="story.txt", data=b"Hello hill.\n")
    assert "Hello" in text


def test_pdf_rejected() -> None:
    try:
        extract_book_text(filename="x.pdf", data=b"%PDF")
    except ValueError as exc:
        assert "PDF" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_epub_rejects_zip_slip_paths() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.xhtml", b"<p>bad</p>")
        archive.writestr("chapter.xhtml", b"<p>Hello hill.</p>")
    text = extract_book_text(filename="story.epub", data=buffer.getvalue())
    assert "Hello" in text
    assert "bad" not in text
