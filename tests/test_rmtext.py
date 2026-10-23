"""Tests for the shared RootsMagic markup dialect.

The dialect is a fact about the RootsMagic file format, so it lives in
rmread. These tests pin the behaviour both consumers depend on:
rmcite renders it, rm2gramps exports it as Gramps style ranges.
"""

from rmread.rmtext import (
    Chunk,
    Span,
    normalize_newlines,
    plain_text,
    tokenize,
)


def test_plain_text_is_one_text_chunk():
    assert tokenize("Hello world") == [
        Chunk(kind="text", text="Hello world"),
    ]


def test_bold_tag_becomes_open_and_close_style_chunks():
    assert tokenize("a <b>real</b> fact") == [
        Chunk(kind="text", text="a "),
        Chunk(kind="style", name="bold"),
        Chunk(kind="text", text="real"),
        Chunk(kind="style", name="bold", closing=True),
        Chunk(kind="text", text=" fact"),
    ]


def test_strong_and_em_are_aliases():
    chunks = tokenize("<strong>a</strong><em>b</em>")
    assert [c.name for c in chunks if c.kind == "style"] == [
        "bold", "bold", "italic", "italic",
    ]


def test_br_becomes_a_break_chunk():
    assert tokenize("one<br>two") == [
        Chunk(kind="text", text="one"),
        Chunk(kind="break"),
        Chunk(kind="text", text="two"),
    ]


def test_anchor_href_becomes_a_link_chunk():
    assert tokenize('<a href="https://x.example">X</a>') == [
        Chunk(kind="link", name="https://x.example"),
        Chunk(kind="text", text="X"),
        Chunk(kind="link", closing=True),
    ]


def test_unknown_tag_is_reported_with_its_source_text():
    """An unknown tag must survive with its exact source text.

    RootsMagic stores note text raw, so a "<" the researcher typed is
    indistinguishable from markup. The consumer decides what to do
    with it; the tokenizer only has to not lose it.
    """
    assert tokenize("by me <assistant curate>") == [
        Chunk(kind="text", text="by me "),
        Chunk(kind="tag", text="<assistant curate>"),
    ]


def test_tokenize_does_not_decode_entities():
    """RM writes raw text, so an entity-looking sequence stays as it is."""
    assert tokenize("Barnes &amp; Noble") == [
        Chunk(kind="text", text="Barnes &amp; Noble"),
    ]


def test_tokenize_does_not_touch_line_endings():
    assert tokenize("a\r\nb") == [Chunk(kind="text", text="a\r\nb")]


def test_normalize_newlines_maps_crlf_and_lone_cr_to_lf():
    assert normalize_newlines("a\r\nb\rc") == "a\nb\nc"


def test_plain_text_removes_known_markup():
    assert plain_text("a <b>real</b> fact").text == "a real fact"


def test_plain_text_reports_a_bold_range_over_the_plain_text():
    assert plain_text("a <b>real</b> fact").spans == [
        Span(style="bold", start=2, end=6),
    ]


def test_plain_text_keeps_unknown_tags_verbatim():
    """Dropping the tag would silently delete transcription text."""
    text = plain_text("by me <assistant curate>").text
    assert text == "by me <assistant curate>"


def test_plain_text_normalises_crlf_and_measures_ranges_on_the_result():
    """XML line-end normalisation is mandatory, so ranges must be
    computed over the normalised text Gramps will actually hold."""
    result = plain_text("one\r\ntwo <b>x</b>")
    assert result.text == "one\ntwo x"
    assert result.spans == [Span(style="bold", start=8, end=9)]


def test_nested_styles_yield_one_range_each():
    result = plain_text("<b><i>x</i></b>")
    assert result.text == "x"
    assert result.spans == [
        Span(style="bold", start=0, end=1),
        Span(style="italic", start=0, end=1),
    ]


def test_link_becomes_a_span_carrying_its_target():
    result = plain_text('see <a href="https://x.example">X</a>')
    assert result.text == "see X"
    assert result.spans == [
        Span(style="link", start=4, end=5, value="https://x.example"),
    ]


def test_break_becomes_a_newline():
    assert plain_text("one<br>two").text == "one\ntwo"
