import io
import zipfile

import pytest
from ebooklib import epub

from app.services.book_analysis import (
    _spacy_nlp,
    analyze_text,
    coverage_curve,
    extract_book_text,
    extract_book_title,
    fallback_lemmatize,
    infer_title_from_text,
    normalize_book_text,
    suspicious_lemma_reason,
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
    assert fallback_lemmatize("conscious") == "conscious"
    assert fallback_lemmatize("focus") == "focus"
    assert fallback_lemmatize("something") == "something"
    assert fallback_lemmatize("nothing") == "nothing"
    assert fallback_lemmatize("anything") == "anything"
    assert fallback_lemmatize("everything") == "everything"


def test_coverage_curve_zipf() -> None:
    freqs = [("a", 50), ("b", 30), ("c", 10), ("d", 5), ("e", 5)]
    curve = coverage_curve(freqs)
    assert curve["50"] == 1
    assert curve["80"] == 2
    assert curve["90"] >= 3


def test_analyze_text_keeps_something_nothing_lemmas() -> None:
    analysis = analyze_text("Something happened and nothing changed.", coverage_target=0.8)
    lemmas = {item.lemma for item in analysis.lemmas}
    assert "something" in lemmas
    assert "nothing" in lemmas
    assert "someth" not in lemmas
    assert "noth" not in lemmas


def test_spacy_lemmatizes_continued_to_continue() -> None:
    if _spacy_nlp() is None:
        pytest.skip("en_core_web_sm not installed")
    analysis = analyze_text("He continued walking and continued again.", coverage_target=0.8)
    lemmas = {item.lemma for item in analysis.lemmas}
    assert analysis.engine == "spacy"
    assert "continue" in lemmas
    assert "continu" not in lemmas


def test_analyze_text_skips_function_words_and_caps_study_set() -> None:
    analysis = analyze_text(FOX_STORY, coverage_target=0.8)
    lemmas = {item.lemma for item in analysis.lemmas}
    assert "the" not in lemmas
    assert "and" not in lemmas
    assert "fox" in lemmas
    assert "b" not in lemmas
    assert "em" not in lemmas
    study = {item.lemma for item in analysis.lemmas if item.in_study_set}
    highest = max(analysis.lemmas, key=lambda item: item.frequency)
    assert highest.lemma in study
    assert len(study) < analysis.content_lemma_count or analysis.content_lemma_count <= 8
    assert analysis.coverage_curve["80"] >= 1
    assert analysis.token_count > 20


@pytest.mark.parametrize(
    ("lemma", "expected"),
    [
        ("b", "single_letter"),
        ("em", "html_artifact"),
        ("br", "html_artifact"),
        ("fox", None),
        ("consciou", "broken_lemma"),
        ("div", "html_artifact"),
    ],
)
def test_suspicious_lemma_reason(lemma: str, expected: str | None) -> None:
    assert suspicious_lemma_reason(lemma) == expected


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
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.xhtml", b"<p>bad</p>")
        archive.writestr("chapter.xhtml", b"<p>Hello hill.</p>")
    text = extract_book_text(filename="story.epub", data=buffer.getvalue())
    assert "Hello" in text
    assert "bad" not in text


def test_extract_book_title_from_txt_first_line() -> None:
    text = "The Adventures of Cano\n\nChapter 1\nThe fox ran."
    data = text.encode()
    title, source = extract_book_title(filename="cano.txt", data=data, text=text)
    assert title == "The Adventures of Cano"
    assert source == "content"


def test_extract_book_title_from_epub_metadata() -> None:
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Charlotte&apos;s Web</dc:title>
      </metadata>
    </package>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("content.opf", opf)
        archive.writestr("chapter.xhtml", b"<p>Some words here.</p>")
    data = buffer.getvalue()
    title, source = extract_book_title(
        filename="short.epub",
        data=data,
        text=extract_book_text(filename="short.epub", data=data),
    )
    assert title == "Charlotte's Web"
    assert source == "metadata"


def test_extract_book_title_falls_back_to_filename() -> None:
    text = "\n\nThe fox ran to the hill."
    title, source = extract_book_title(filename="cano.txt", data=text.encode(), text=text)
    assert title == "cano"
    assert source == "filename"


def test_infer_title_skips_chapter_headings() -> None:
    text = "Chapter 1\n\nThe Real Book Title\n\nBody text."
    assert infer_title_from_text(text) == "The Real Book Title"


def _make_epub_bytes(chapters: list[tuple[str, str]]) -> bytes:
    book = epub.EpubBook()
    book.set_identifier("test-book-id")
    book.set_title("Test Book")
    book.set_language("en")

    spine: list = ["nav"]
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    for file_name, body_html in chapters:
        chapter = epub.EpubHtml(title=file_name, file_name=file_name, lang="en")
        chapter.content = (
            f"<html><head></head><body>{body_html}</body></html>".encode()
        )
        book.add_item(chapter)
        spine.append(chapter)

    book.spine = spine
    buffer = io.BytesIO()
    epub.write_epub(buffer, book, {})
    return buffer.getvalue()


def _lemma_set_from_epub(chapters: list[tuple[str, str]]) -> set[str]:
    data = _make_epub_bytes(chapters)
    text = extract_book_text(filename="story.epub", data=data)
    analysis = analyze_text(text, coverage_target=0.8)
    return {item.lemma for item in analysis.lemmas}


def test_normalize_book_text_joins_line_break_hyphen() -> None:
    assert normalize_book_text("every-\nthing") == "everything"


def test_normalize_book_text_removes_soft_hyphen() -> None:
    assert normalize_book_text("con\u00adscious") == "conscious"


def test_epub_split_span_word_stays_whole() -> None:
    lemmas = _lemma_set_from_epub(
        [("chap_01.xhtml", "<p>She was consci<span>ous</span> today.</p>")],
    )
    assert "conscious" in lemmas
    assert "consci" not in lemmas
    assert "ous" not in lemmas


def test_epub_soft_hyphen_entity_stays_whole() -> None:
    lemmas = _lemma_set_from_epub(
        [("chap_01.xhtml", "<p>She was con&shy;scious today.</p>")],
    )
    assert "conscious" in lemmas
    assert "consci" not in lemmas


def test_epub_line_break_hyphen_stays_whole() -> None:
    data = _make_epub_bytes([("chap_01.xhtml", "<p>The win-\nter was cold.</p>")])
    text = extract_book_text(filename="story.epub", data=data)
    assert "winter" in text
    assert "win ter" not in text
    analysis = analyze_text(text, coverage_target=0.8)
    lemmas = {item.lemma for item in analysis.lemmas}
    assert "winter" in lemmas
    assert "win" not in lemmas


def test_txt_line_break_hyphen_stays_whole() -> None:
    text = extract_book_text(filename="story.txt", data=b"The win-\nter was cold.")
    assert "winter" in text
    analysis = analyze_text(text, coverage_target=0.8)
    lemmas = {item.lemma for item in analysis.lemmas}
    assert "winter" in lemmas


def test_epub_spine_order_not_alphabetical() -> None:
    data = _make_epub_bytes(
        [
            ("chap_02.xhtml", "<p>second chapter marker</p>"),
            ("chap_10.xhtml", "<p>tenth chapter marker</p>"),
        ],
    )
    text = extract_book_text(filename="story.epub", data=data)
    assert text.index("second") < text.index("tenth")
