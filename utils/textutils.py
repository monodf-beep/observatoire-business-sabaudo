"""Nettoyage de texte : conversion HTML -> texte et normalisation.

Implémentation 100% bibliothèque standard (pas de dépendance externe),
conformément à la liste de librairies du Sprint 1.
"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_BLOCK_TAGS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "head"}


class _TextExtractor(HTMLParser):
    """Extrait le texte visible d'un fragment HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def html_to_text(html: str) -> str:
    """Convertit du HTML en texte brut (robuste aux fragments mal formés)."""
    if not html:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Repli : on retire grossièrement les balises
        return clean_text(unescape(re.sub(r"<[^>]+>", " ", html)))
    return clean_text(parser.get_text())


def clean_text(text: str) -> str:
    """Normalise les espaces et lignes vides d'un texte."""
    if not text:
        return ""
    text = unescape(text)
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
