"""The RootsMagic HTML-ish markup dialect.

RootsMagic stores note-like text -- inline notes on a person or event,
a source or citation transcription, a media description -- as a small
HTML-ish dialect: a handful of tags around plain text. That dialect is
a fact about the RootsMagic file format, so it lives here in rmread,
the shared read-side library.

Two consumers, two policies:

* ``rmcite`` renders the text for a human reader. It drops tags it
  does not know and decodes HTML entities.
* ``rm2gramps`` exports the text into a Gramps XML file. It keeps
  unknown tags verbatim, because RootsMagic stores note text *raw* --
  a "<" the researcher typed is indistinguishable from markup, and
  silently deleting transcription text is evidence loss.

So the tokenizer here does neither of those things. It reports what it
found and leaves the policy to the caller:

* :func:`tokenize` -- the markup as a list of chunks.
* :func:`plain_text` -- the text with known markup resolved, plus the
  style ranges over it.
* :func:`normalize_newlines` -- CRLF and lone CR to LF.

The range convention is half-open: ``text[start:end]`` is the styled
run. That matches Gramps' own ``StyledText`` handling and the range
values in Gramps' own XML files.

Nothing in here knows what a Gramps note is. The Gramps-specific parts
-- type names, the ``<style>``/``<range>`` elements, the DTD's element
order -- stay in rm2gramps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Tag names that carry a character style, mapped to the style name.
STYLE_TAGS = {
    "b": "bold",
    "strong": "bold",
    "i": "italic",
    "em": "italic",
}

#: The tag whose attribute carries a URL.
LINK_TAG = "a"

#: The tag that means "line break".
BREAK_TAG = "br"

#: A tag, with an optional attribute payload. Deliberately narrow: it
#: matches the dialect RootsMagic actually writes, not all of HTML.
_TAG_RE = re.compile(
    r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9]*)([^>]*?)\s*(/?)\s*>"
)

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']*)["']""")


@dataclass(frozen=True)
class Chunk:
    """One piece of a tokenized markup string.

    ``kind`` is one of:

    ``"text"``
        Literal text. ``text`` holds it, undecoded: RootsMagic writes
        raw text, so ``&amp;`` in a note is five characters the
        researcher typed, not an entity.
    ``"style"``
        An opening or closing character-style tag. ``name`` is the
        style ("bold", "italic"); ``closing`` says which.
    ``"link"``
        An opening or closing anchor. ``name`` is the URL on an
        opening tag; ``closing`` says which.
    ``"break"``
        A line break.
    ``"tag"``
        A tag this dialect does not know. ``text`` holds the tag's
        exact source text, so a consumer that wants to keep it can.
    """

    kind: str
    text: str = ""
    name: str = ""
    closing: bool = False


@dataclass(frozen=True)
class Span:
    """A styled run over a plain-text string.

    ``start`` is inclusive, ``end`` exclusive -- ``text[start:end]``
    is the run. ``value`` carries the URL for a ``"link"`` span and is
    empty otherwise.
    """

    style: str
    start: int
    end: int
    value: str = ""


@dataclass(frozen=True)
class PlainText:
    """Markup resolved to plain text plus the style ranges over it."""

    text: str
    spans: list[Span]


def normalize_newlines(s: str) -> str:
    """Map CRLF and lone CR to LF.

    XML line-end normalisation is mandatory: a parser converts CRLF to
    LF in content. Gramps' importer stores what the parser hands it,
    so any character offset computed against the un-normalised text
    would be wrong after the first line break.
    """
    return s.replace("\r\n", "\n").replace("\r", "\n")


def tokenize(markup: str) -> list[Chunk]:
    """Split RootsMagic markup into chunks.

    Line endings and entities are left exactly as they are; this
    function only says where the tags are and what they mean.
    """
    chunks: list[Chunk] = []
    pos = 0
    for m in _TAG_RE.finditer(markup):
        if m.start() > pos:
            chunks.append(Chunk(kind="text", text=markup[pos:m.start()]))
        closing = m.group(1) == "/"
        tag = m.group(2).lower()
        attrs = m.group(3)
        if tag in STYLE_TAGS:
            chunks.append(
                Chunk(kind="style", name=STYLE_TAGS[tag], closing=closing)
            )
        elif tag == BREAK_TAG:
            chunks.append(Chunk(kind="break"))
        elif tag == LINK_TAG:
            href = ""
            if not closing:
                href_match = _HREF_RE.search(attrs)
                if href_match:
                    href = href_match.group(1)
            chunks.append(Chunk(kind="link", name=href, closing=closing))
        else:
            # Unknown tag: hand back its exact source text so the
            # consumer can keep it.
            chunks.append(Chunk(kind="tag", text=m.group(0)))
        pos = m.end()
    if pos < len(markup):
        chunks.append(Chunk(kind="text", text=markup[pos:]))
    return chunks


def plain_text(markup: str) -> PlainText:
    """Resolve RootsMagic markup to plain text and style ranges.

    Known markup (``<b>``, ``<i>``, ``<br>``, ``<a href>``) is
    resolved: style tags become ranges over the plain text, a break
    becomes a newline, and a link becomes a ``"link"`` span carrying
    its URL. Unknown tags are kept verbatim, entities are not decoded,
    and line endings are normalised to LF before any offset is
    measured -- so the returned ranges index the returned text.

    Parameters
    ----------
    markup
        The raw RootsMagic markup.

    Returns
    -------
    PlainText
        The text and its style ranges.
    """
    text_parts: list[str] = []
    spans: list[Span] = []
    style_stack: list[str] = []
    link_stack: list[str] = []
    length = 0

    def _emit(chunk_text: str) -> None:
        nonlocal length
        if not chunk_text:
            return
        start = length
        text_parts.append(chunk_text)
        length += len(chunk_text)
        for style in style_stack:
            spans.append(Span(style=style, start=start, end=length))
        if link_stack:
            spans.append(
                Span(
                    style="link",
                    start=start,
                    end=length,
                    value=link_stack[-1],
                )
            )

    for chunk in tokenize(normalize_newlines(markup)):
        if chunk.kind == "text":
            _emit(chunk.text)
        elif chunk.kind == "style":
            if chunk.closing:
                if style_stack and style_stack[-1] == chunk.name:
                    style_stack.pop()
            else:
                style_stack.append(chunk.name)
        elif chunk.kind == "link":
            if chunk.closing:
                if link_stack:
                    link_stack.pop()
            else:
                link_stack.append(chunk.name)
        elif chunk.kind == "break":
            _emit("\n")
        else:
            # Unknown tag: keep it verbatim.
            _emit(chunk.text)

    return PlainText(text="".join(text_parts), spans=spans)
