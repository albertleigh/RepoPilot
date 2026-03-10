"""Markdown → Qt-compatible HTML renderer.

Uses the ``markdown`` library when available (with fenced-code and tables);
falls back to a lightweight regex-based converter otherwise.
"""
from __future__ import annotations

import re
from html import escape

try:
    import markdown as _md

    _HAS_MARKDOWN = True
except ImportError:
    _HAS_MARKDOWN = False


def render_markdown(
    text: str,
    code_bg: str = "#1e1e2e",
    code_fg: str = "#cdd6f4",
) -> str:
    """Convert *text* from Markdown to HTML suitable for Qt rich-text widgets."""
    if _HAS_MARKDOWN:
        html = _md.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
        )
    else:
        html = _fallback(text)
    return _inject_code_styles(html, code_bg, code_fg)


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

_CODE_STYLE = (
    "font-family:'Consolas','Courier New',monospace; font-size:12px;"
)


def _inject_code_styles(html: str, code_bg: str, code_fg: str) -> str:
    """Add inline styles to ``<pre>`` and ``<code>`` elements."""
    block_style = (
        f"background-color:{code_bg}; color:{code_fg}; "
        f"padding:8px 10px; border-radius:6px; "
        f"white-space:pre-wrap; word-wrap:break-word; {_CODE_STYLE}"
    )
    inline_style = (
        f"background-color:{code_bg}; color:{code_fg}; "
        f"padding:1px 5px; border-radius:3px; {_CODE_STYLE}"
    )
    # Block code: <pre> (may already contain <code>)
    html = html.replace("<pre>", f'<pre style="{block_style}">')
    # Inline code: <code> NOT already inside a styled <pre>
    html = re.sub(
        r"<code(?!\s*style=)(?!\s*class=)>",
        f'<code style="{inline_style}">',
        html,
    )
    return html


def _fallback(text: str) -> str:
    """Minimal Markdown-like rendering without external libraries."""
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                out.append("</code></pre>")
            else:
                out.append("<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            out.append(escape(line) + "\n")
            continue
        rendered = escape(line)
        rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
        rendered = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", rendered)
        rendered = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", rendered)
        out.append(rendered + "<br>")
    if in_code:
        out.append("</code></pre>")
    return "".join(out)
