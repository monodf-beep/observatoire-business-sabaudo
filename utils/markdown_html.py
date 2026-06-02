"""Conversion Markdown -> HTML pour l'email Brevo.

Utilise la bibliothèque `markdown` si présente (rendu complet : titres, listes,
gras, liens, tableaux). À défaut, un convertisseur minimal de secours évite tout
plantage. Le fragment produit est ensuite habillé d'un gabarit HTML d'email
sobre et responsive (styles en ligne, compatibles clients mail).
"""
from __future__ import annotations

import re
from html import escape


def md_to_html_fragment(text: str) -> str:
    """Convertit du Markdown en fragment HTML."""
    try:
        import markdown  # dépendance optionnelle (voir requirements.txt)

        return markdown.markdown(text, extensions=["extra", "sane_lists", "nl2br"])
    except ImportError:
        return _minimal_md(text)


def _inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _minimal_md(text: str) -> str:
    """Convertisseur de secours (titres, listes, citations, paragraphes)."""
    html: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if re.match(r"^#{1,6}\s", line):
            level = len(line) - len(line.lstrip("#"))
            level = min(level, 6)
            html.append(f"<h{level}>{_inline(line.lstrip('# ').strip())}</h{level}>")
            i += 1
        elif re.match(r"^(-{3,}|\*{3,})$", line):
            html.append("<hr>")
            i += 1
        elif re.match(r"^\s*[-*+]\s", line):
            items = []
            while i < n and re.match(r"^\s*[-*+]\s", lines[i]):
                content = _inline(re.sub(r"^\s*[-*+]\s+", "", lines[i]))
                items.append(f"<li>{content}</li>")
                i += 1
            html.append("<ul>" + "".join(items) + "</ul>")
        elif re.match(r"^\s*\d+\.\s", line):
            items = []
            while i < n and re.match(r"^\s*\d+\.\s", lines[i]):
                content = _inline(re.sub(r"^\s*\d+\.\s+", "", lines[i]))
                items.append(f"<li>{content}</li>")
                i += 1
            html.append("<ol>" + "".join(items) + "</ol>")
        elif line.lstrip().startswith(">"):
            quote = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote.append(_inline(re.sub(r"^\s*>\s?", "", lines[i])))
                i += 1
            html.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
        else:
            para = []
            while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|\s*[-*+]\s|\s*\d+\.\s|>|-{3,})", lines[i]):
                para.append(_inline(lines[i].strip()))
                i += 1
            html.append("<p>" + "<br>".join(para) + "</p>")
    return "\n".join(html)


_BODY_STYLE = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,"
    "Arial,sans-serif;color:#1a1a1a;line-height:1.6;margin:0;padding:0;"
    "background:#f4f5f7;"
)
_CONTAINER_STYLE = (
    "max-width:640px;margin:0 auto;padding:32px 28px;background:#ffffff;"
)


def wrap_email_html(fragment_html: str, title: str) -> str:
    """Habille un fragment HTML d'un gabarit d'email complet et autonome."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="fr">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>{escape(title)}</title>\n"
        "</head>\n"
        f'<body style="{_BODY_STYLE}">\n'
        f'<div style="{_CONTAINER_STYLE}">\n'
        f"{fragment_html}\n"
        "</div>\n</body>\n</html>\n"
    )
