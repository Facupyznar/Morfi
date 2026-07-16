import html
import re

from markupsafe import Markup


_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\d+\.\s+(.*)$")


def _safe_href(raw_href):
    href = (raw_href or "").strip()
    if href.startswith(("http://", "https://", "mailto:", "/")):
        return html.escape(href, quote=True)
    return "#"


def _render_inline(text):
    escaped = html.escape(text or "")
    escaped = _INLINE_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    escaped = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", escaped)
    escaped = _LINK_RE.sub(
        lambda m: (
            f'<a href="{_safe_href(m.group(2))}" target="_blank" rel="noopener noreferrer">'
            f"{m.group(1)}</a>"
        ),
        escaped,
    )
    return escaped.replace("\n", "<br>")


def render_markdown(value):
    raw_text = (value or "").replace("\r\n", "\n").strip()
    if not raw_text:
        return Markup("")

    blocks = re.split(r"\n\s*\n", raw_text)
    rendered_blocks = []

    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        heading_match = _HEADING_RE.match(lines[0])
        if len(lines) == 1 and heading_match:
            level = len(heading_match.group(1))
            content = _render_inline(heading_match.group(2).strip())
            rendered_blocks.append(f"<h{level}>{content}</h{level}>")
            continue

        if all(_UL_RE.match(line) for line in lines):
            items = "".join(f"<li>{_render_inline(_UL_RE.match(line).group(1).strip())}</li>" for line in lines)
            rendered_blocks.append(f"<ul>{items}</ul>")
            continue

        if all(_OL_RE.match(line) for line in lines):
            items = "".join(f"<li>{_render_inline(_OL_RE.match(line).group(1).strip())}</li>" for line in lines)
            rendered_blocks.append(f"<ol>{items}</ol>")
            continue

        rendered_blocks.append(f"<p>{_render_inline(block.strip())}</p>")

    return Markup("".join(rendered_blocks))
