"""Offline book vocabulary analysis — tokenize, lemma, coverage curve.

spaCy is optional. Tests and CI use the fallback tokenizer so they stay offline.
When ``en_core_web_sm`` is installed, analyze_text prefers that pipeline
(tokenize + POS + lemma + NER). Do not disable NER/parser/attribute_ruler.
"""

from __future__ import annotations

import html
import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

import ebooklib
from ebooklib import epub
from lxml import etree

logger = logging.getLogger(__name__)

# NLTK English stopwords (same set the Sherlock research used).
FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "ain",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren",
        "aren't",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "couldn",
        "couldn't",
        "d",
        "did",
        "didn",
        "didn't",
        "do",
        "does",
        "doesn",
        "doesn't",
        "doing",
        "don",
        "don't",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "hadn",
        "hadn't",
        "has",
        "hasn",
        "hasn't",
        "have",
        "haven",
        "haven't",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "isn",
        "isn't",
        "it",
        "it's",
        "its",
        "itself",
        "just",
        "ll",
        "m",
        "ma",
        "me",
        "mightn",
        "mightn't",
        "more",
        "most",
        "mustn",
        "mustn't",
        "my",
        "myself",
        "needn",
        "needn't",
        "no",
        "nor",
        "not",
        "now",
        "o",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "re",
        "s",
        "same",
        "shan",
        "shan't",
        "she",
        "she's",
        "should",
        "should've",
        "shouldn",
        "shouldn't",
        "so",
        "some",
        "such",
        "t",
        "than",
        "that",
        "that'll",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "ve",
        "very",
        "was",
        "wasn",
        "wasn't",
        "we",
        "were",
        "weren",
        "weren't",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "won",
        "won't",
        "wouldn",
        "wouldn't",
        "y",
        "you",
        "you'd",
        "you'll",
        "you're",
        "you've",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)

NER_LABELS = frozenset({"PERSON", "GPE", "ORG", "LOC", "NORP", "FAC"})

COVERAGE_BREAKPOINTS = (0.5, 0.8, 0.9, 0.95, 0.98, 0.99)
DEFAULT_COVERAGE_TARGET = 0.80

TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
HTML_TAG_RE = re.compile(r"<[^>]+>")
SENTENCE_END_RE = re.compile(r"[.!?]")
_LINE_BREAK_HYPHEN_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_SOFT_HYPHEN_CHARS = ("\u00ad", "\u200b")
_HTML_PARSER = etree.HTMLParser()

MIN_CONTENT_LEMMA_LENGTH = 3

HTML_ARTIFACTS: frozenset[str] = frozenset(
    {
        "em",
        "br",
        "li",
        "td",
        "th",
        "ul",
        "ol",
        "hr",
        "div",
        "span",
        "img",
        "src",
        "href",
        "alt",
        "rel",
        "var",
        "sub",
        "sup",
        "nav",
        "svg",
        "xml",
        "meta",
        "head",
        "body",
        "html",
        "pre",
        "code",
    }
)

BROKEN_LEMMA_RE = re.compile(r"(?:consciou|familiou|iou)$")


def suspicious_lemma_reason(lemma: str) -> str | None:
    """Return a reason code when a book lemma looks like junk, else None."""
    normalized = lemma.strip().lower()
    if not normalized:
        return "non_alpha"
    if not normalized.isalpha():
        return "non_alpha"
    if len(normalized) == 1:
        return "single_letter"
    if normalized in HTML_ARTIFACTS:
        return "html_artifact"
    if len(normalized) < MIN_CONTENT_LEMMA_LENGTH:
        return "too_short"
    if BROKEN_LEMMA_RE.search(normalized):
        return "broken_lemma"
    return None


_IRREGULAR: dict[str, str] = {
    "am": "be",
    "are": "be",
    "is": "be",
    "was": "be",
    "were": "be",
    "been": "be",
    "being": "be",
    "has": "have",
    "had": "have",
    "having": "have",
    "does": "do",
    "did": "do",
    "doing": "do",
    "done": "do",
    "went": "go",
    "gone": "go",
    "going": "go",
    "ran": "run",
    "running": "run",
    "came": "come",
    "coming": "come",
    "saw": "see",
    "seen": "see",
    "seeing": "see",
    "took": "take",
    "taken": "take",
    "taking": "take",
    "got": "get",
    "getting": "get",
    "made": "make",
    "making": "make",
    "said": "say",
    "saying": "say",
    "knew": "know",
    "known": "know",
    "knowing": "know",
    "thought": "think",
    "thinking": "think",
    "ate": "eat",
    "eaten": "eat",
    "eating": "eat",
    "woke": "wake",
    "woken": "wake",
    "waking": "wake",
    "mice": "mouse",
    "children": "child",
    "men": "man",
    "women": "woman",
    "feet": "foot",
    "teeth": "tooth",
    "geese": "goose",
}

_SPACY_NLP = None
_SPACY_TRIED = False


@dataclass(frozen=True)
class LemmaCount:
    lemma: str
    frequency: int
    rank: int
    in_study_set: bool


@dataclass
class BookAnalysis:
    token_count: int
    unique_lemma_count: int
    content_lemma_count: int
    skipped_function_words: int
    skipped_proper_nouns: int
    coverage_curve: dict[str, int]
    lemmas: list[LemmaCount] = field(default_factory=list)
    engine: str = "fallback"

    def study_set(self, coverage_target: float = DEFAULT_COVERAGE_TARGET) -> list[LemmaCount]:
        return apply_coverage_cap(self.lemmas, coverage_target)


_ING_LEMMA_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "something",
        "anything",
        "everything",
        "nothing",
    }
)


def fallback_lemmatize(token: str) -> str:
    lower = token.lower()
    if lower in _IRREGULAR:
        return _IRREGULAR[lower]
    if lower.endswith("ies") and len(lower) > 4:
        return lower[:-3] + "y"
    if (
        any(lower.endswith(sfx) for sfx in ("ches", "shes", "sses", "xes", "zes"))
        and len(lower) > 4
    ):
        return lower[:-2]
    if lower.endswith("ing") and len(lower) > 5:
        if lower in _ING_LEMMA_EXCEPTIONS:
            return lower
        stem = lower[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
            stem = stem[:-1]
        return stem
    if lower.endswith("ed") and len(lower) > 4:
        stem = lower[:-2]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
            stem = stem[:-1]
        return stem
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) > 3:
        # Keep -ous/-us/-is (conscious, focus, basis) — naive -s strip breaks them.
        if not lower.endswith(("ous", "us", "is")):
            return lower[:-1]
    return lower


def _spacy_nlp():
    global _SPACY_NLP, _SPACY_TRIED
    if _SPACY_TRIED:
        return _SPACY_NLP
    _SPACY_TRIED = True
    try:
        import spacy

        _SPACY_NLP = spacy.load("en_core_web_sm")
    except Exception:
        _SPACY_NLP = None
    return _SPACY_NLP


def coverage_curve(lemma_freqs: list[tuple[str, int]]) -> dict[str, int]:
    """Return lemma counts at coverage breakpoints of the given frequency list."""
    total = sum(freq for _, freq in lemma_freqs)
    if total <= 0:
        return {str(int(p * 100)): 0 for p in COVERAGE_BREAKPOINTS}
    curve: dict[str, int] = {}
    remaining = list(COVERAGE_BREAKPOINTS)
    running = 0
    for index, (_, freq) in enumerate(lemma_freqs, start=1):
        running += freq
        while remaining and running / total >= remaining[0]:
            curve[str(int(remaining[0] * 100))] = index
            remaining = remaining[1:]
        if not remaining:
            break
    last = len(lemma_freqs)
    for point in remaining:
        curve[str(int(point * 100))] = last
    return curve


def apply_coverage_cap(lemmas: list[LemmaCount], coverage_target: float) -> list[LemmaCount]:
    target = max(0.5, min(coverage_target, 0.99))
    total = sum(item.frequency for item in lemmas)
    if total <= 0:
        return []
    running = 0
    selected: list[LemmaCount] = []
    for item in lemmas:
        selected.append(
            LemmaCount(
                lemma=item.lemma,
                frequency=item.frequency,
                rank=item.rank,
                in_study_set=True,
            )
        )
        running += item.frequency
        if running / total >= target:
            break
    return selected


def _analyze_fallback(text: str) -> tuple[list[tuple[str, str, bool]], str]:
    """Return (surface, lemma, is_proper) tokens plus engine name."""
    tokens: list[tuple[str, str, bool]] = []
    sentence_start = True
    last_end = 0
    for match in TOKEN_RE.finditer(text):
        gap = text[last_end : match.start()]
        if SENTENCE_END_RE.search(gap):
            sentence_start = True
        surface = match.group(0)
        last_end = match.end()
        if "'" in surface:
            sentence_start = False
            continue
        if not surface.isalpha():
            continue
        lemma = fallback_lemmatize(surface)
        is_proper = surface[:1].isupper() and not sentence_start and surface[1:].islower()
        tokens.append((surface, lemma, is_proper))
        sentence_start = False
    return tokens, "fallback"


def _analyze_spacy(text: str, nlp) -> tuple[list[tuple[str, str, bool]], str]:
    tokens: list[tuple[str, str, bool]] = []
    for doc in nlp.pipe([text], batch_size=1):
        proper_spans = set()
        for ent in doc.ents:
            if ent.label_ in NER_LABELS:
                proper_spans.update(range(ent.start, ent.end))
        for index, token in enumerate(doc):
            if not token.is_alpha:
                continue
            lemma = token.lemma_.lower().strip()
            if not lemma:
                continue
            is_proper = index in proper_spans
            tokens.append((token.text, lemma, is_proper))
    return tokens, "spacy"


def analyze_text(text: str, *, coverage_target: float = DEFAULT_COVERAGE_TARGET) -> BookAnalysis:
    nlp = _spacy_nlp()
    if nlp is not None:
        tagged, engine = _analyze_spacy(text, nlp)
    else:
        tagged, engine = _analyze_fallback(text)

    alpha_tokens = [(surface, lemma, is_proper) for surface, lemma, is_proper in tagged if lemma]
    token_count = len(alpha_tokens)

    function_skipped = 0
    proper_skipped = 0
    unique_lemmas: set[str] = set()
    content_freq: dict[str, int] = {}

    for _surface, lemma, is_proper in alpha_tokens:
        unique_lemmas.add(lemma)
        if lemma in FUNCTION_WORDS:
            function_skipped += 1
            continue
        if len(lemma) < MIN_CONTENT_LEMMA_LENGTH:
            function_skipped += 1
            continue
        if is_proper:
            proper_skipped += 1
            continue
        content_freq[lemma] = content_freq.get(lemma, 0) + 1

    ranked = sorted(content_freq.items(), key=lambda item: (-item[1], item[0]))
    curve = coverage_curve(ranked)
    cap_count = 0
    content_total = sum(content_freq.values())
    running = 0
    target = max(0.5, min(coverage_target, 0.99))
    if content_total > 0:
        for index, (_lemma, freq) in enumerate(ranked, start=1):
            running += freq
            cap_count = index
            if running / content_total >= target:
                break

    lemmas = [
        LemmaCount(lemma=lemma, frequency=freq, rank=index, in_study_set=index <= cap_count)
        for index, (lemma, freq) in enumerate(ranked, start=1)
    ]
    return BookAnalysis(
        token_count=token_count,
        unique_lemma_count=len(unique_lemmas),
        content_lemma_count=len(content_freq),
        skipped_function_words=function_skipped,
        skipped_proper_nouns=proper_skipped,
        coverage_curve=curve,
        lemmas=lemmas,
        engine=engine,
    )


def extract_txt(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _safe_zip_member(name: str) -> bool:
    """Reject zip-slip and absolute paths."""
    if not name or name.startswith("/") or ".." in name.split("/"):
        return False
    return name.lower().endswith((".xhtml", ".html", ".htm"))


def normalize_book_text(text: str) -> str:
    for char in _SOFT_HYPHEN_CHARS:
        text = text.replace(char, "")
    text = _LINE_BREAK_HYPHEN_RE.sub(r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def _html_bytes_to_text(raw: bytes) -> str:
    try:
        root = etree.fromstring(raw, parser=_HTML_PARSER)
    except etree.XMLSyntaxError:
        return html.unescape(HTML_TAG_RE.sub(" ", extract_txt(raw)))
    text = etree.ElementTree(root).xpath("string()")
    return html.unescape(text)


def _extract_epub_regex_fallback(data: bytes) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if _safe_zip_member(name)]
        names.sort()
        for name in names:
            raw = archive.read(name)
            text = HTML_TAG_RE.sub(" ", extract_txt(raw))
            chunks.append(html.unescape(text))
    return "\n".join(chunks)


def extract_epub(data: bytes) -> str:
    try:
        book = epub.read_epub(io.BytesIO(data), options={"ignore_ncx": True})
    except Exception as exc:
        logger.warning("ebooklib.read_epub failed, falling back to regex extraction: %s", exc)
        return _extract_epub_regex_fallback(data)

    chunks: list[str] = []
    for item_id, linear in book.spine:
        if linear != "yes":
            continue
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        if item.get_type() == ebooklib.ITEM_NAVIGATION:
            continue
        content = item.get_content()
        if not content:
            continue
        text = _html_bytes_to_text(content)
        if text.strip():
            chunks.append(text)

    if not chunks:
        logger.warning("ebooklib spine extraction returned no text, falling back to regex")
        return _extract_epub_regex_fallback(data)

    return "\n\n".join(chunks)


def extract_book_text(*, filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        raise ValueError("PDF upload is not supported yet — use txt or epub.")
    if lower.endswith(".epub"):
        text = extract_epub(data)
    elif lower.endswith(".txt"):
        text = extract_txt(data)
    else:
        raise ValueError("Unsupported file type. Upload a .txt or .epub file.")
    return normalize_book_text(text)


def title_from_filename(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    cleaned = re.sub(r"[_-]+", " ", stem).strip()
    return cleaned[:255] or "Untitled book"


_TITLE_LINE_RE = re.compile(r"^title\s*:\s*(.+)$", re.IGNORECASE)
_CHAPTER_LINE_RE = re.compile(r"^(chapter|part|section|book)\s+[\dIVXLC]+", re.IGNORECASE)


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def extract_epub_title(data: bytes) -> str | None:
    """Read dc:title from EPUB package metadata."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        opf_names = sorted(name for name in archive.namelist() if name.lower().endswith(".opf"))
        for name in opf_names:
            try:
                root = ET.fromstring(archive.read(name))
            except ET.ParseError:
                continue
            for elem in root.iter():
                if _local_tag(elem.tag) != "title":
                    continue
                text = (elem.text or "").strip()
                if text and len(text) >= 2:
                    return html.unescape(text)[:255]
    return None


_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


def extract_epub_heading_title(data: bytes) -> str | None:
    """First chapter h1 as a fallback when OPF metadata is missing."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(name for name in archive.namelist() if _safe_zip_member(name))
        for name in names[:5]:
            raw = archive.read(name)
            match = _H1_RE.search(extract_txt(raw))
            if not match:
                continue
            title = HTML_TAG_RE.sub(" ", match.group(1))
            title = html.unescape(title).strip()
            if len(title) >= 3:
                return title[:255]
    return None


def infer_title_from_text(text: str) -> str | None:
    """Use an explicit Title: line or the first line that looks like a book title."""
    lines = [line.strip() for line in text.splitlines()]
    for line in lines[:30]:
        match = _TITLE_LINE_RE.match(line)
        if match:
            title = match.group(1).strip()
            if len(title) >= 2:
                return title[:255]

    for line in lines[:20]:
        if not line or len(line) < 3 or len(line) > 100:
            continue
        if _CHAPTER_LINE_RE.match(line):
            continue
        if line.endswith(".") and len(line.split()) > 4:
            continue
        if line.count(".") > 1 and len(line.split()) > 10:
            continue
        if len(line.split()) > 12:
            continue
        return line[:255]
    return None


def extract_book_title(*, filename: str, data: bytes, text: str) -> tuple[str, str]:
    """Return (title, source) — source is metadata | content | filename."""
    if filename.lower().endswith(".epub"):
        epub_title = extract_epub_title(data)
        if epub_title:
            return epub_title, "metadata"
        heading = extract_epub_heading_title(data)
        if heading:
            return heading, "content"
    text_title = infer_title_from_text(text)
    filename_title = title_from_filename(filename)
    if text_title:
        if text_title.casefold() != filename_title.casefold() or len(text_title.split()) >= 3:
            return text_title, "content"
    return filename_title, "filename"
