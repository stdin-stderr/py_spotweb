import html
import re
from urllib.parse import urlparse


def _is_valid_url(url: str) -> bool:
    """Check if URL has safe protocol (http/https only)."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')
    except Exception:
        return False


def _escape_html_content(text: str) -> str:
    """Escape HTML special characters in text content."""
    return html.escape(text)


def format_description(text: str) -> str:
    """
    Format description text with full BBCode support.

    Processes (in order):
    - [b]...[/b] → <b>...</b> (bold)
    - [i]...[/i] → <em>...</em> (italic)
    - [u]...[/u] → <u>...</u> (underline)
    - [s]...[/s] → <s>...</s> (strikethrough)
    - [color=#RRGGBB]...[/color] → <span style="color:#RRGGBB">...</span>
    - [url=HREF]text[/url] → <a href="HREF" rel="noopener">text</a>
    - [url]HREF[/url] → <a href="HREF" rel="noopener">HREF</a>
    - [img]URL[/img] → <img src="URL" alt="image">
    - [quote]...[/quote] → <blockquote>...</blockquote>
    - [br] → <br>

    HTML is escaped first to prevent injection.
    Invalid or unmatched tags are left as plain text.

    Args:
        text: Raw description text from database

    Returns:
        HTML-safe formatted text ready for display
    """
    if not text:
        return ""

    # Escape HTML first (prevents injection)
    escaped = _escape_html_content(text)

    # Process simple self-closing tag first
    escaped = re.sub(r'\[br\]', '<br>', escaped, flags=re.IGNORECASE)

    # Process paired tags with content (non-greedy matching)
    # Order matters - more specific patterns first

    # [color=#RRGGBB]...[/color]
    def replace_color(match):
        color_code = match.group(1)
        content = match.group(2)
        # Validate hex color or simple color names
        if re.match(r'^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$', color_code) or re.match(r'^[a-zA-Z]+$', color_code):
            return f'<span style="color:{color_code}">{content}</span>'
        return match.group(0)  # Return unmodified if invalid

    escaped = re.sub(r'\[color=([#\w]+)\](.*?)\[/color\]', replace_color, escaped, flags=re.IGNORECASE | re.DOTALL)

    # [url=HREF]text[/url] - with href attribute
    def replace_url_with_href(match):
        href = match.group(1)
        text = match.group(2)
        if _is_valid_url(href):
            # Escape href for HTML attribute, escape text content
            safe_href = html.escape(href, quote=True)
            return f'<a href="{safe_href}" rel="noopener">{text}</a>'
        return match.group(0)  # Return unmodified if invalid protocol

    escaped = re.sub(r'\[url=([^\]]+)\](.*?)\[/url\]', replace_url_with_href, escaped, flags=re.IGNORECASE | re.DOTALL)

    # [url]HREF[/url] - shorthand, URL is both href and text
    def replace_url_shorthand(match):
        url = match.group(1).strip()
        if _is_valid_url(url):
            safe_url = html.escape(url, quote=True)
            safe_text = html.escape(url)  # URL is also the display text
            return f'<a href="{safe_url}" rel="noopener">{safe_text}</a>'
        return match.group(0)

    escaped = re.sub(r'\[url\](.*?)\[/url\]', replace_url_shorthand, escaped, flags=re.IGNORECASE | re.DOTALL)

    # [img]URL[/img]
    def replace_img(match):
        url = match.group(1).strip()
        if _is_valid_url(url):
            safe_url = html.escape(url, quote=True)
            return f'<img src="{safe_url}" alt="image">'
        return match.group(0)

    escaped = re.sub(r'\[img\](.*?)\[/img\]', replace_img, escaped, flags=re.IGNORECASE | re.DOTALL)

    # [quote]...[/quote]
    escaped = re.sub(r'\[quote\](.*?)\[/quote\]', r'<blockquote>\1</blockquote>', escaped, flags=re.IGNORECASE | re.DOTALL)

    # Simple formatting tags (handle start/end tags independently for better robustness with malformed/nested BBCode)
    # [b]...[/b]
    escaped = re.sub(r'\[b\]', '<b>', escaped, flags=re.IGNORECASE)
    escaped = re.sub(r'\[/b\]', '</b>', escaped, flags=re.IGNORECASE)

    # [i]...[/i]
    escaped = re.sub(r'\[i\]', '<em>', escaped, flags=re.IGNORECASE)
    escaped = re.sub(r'\[/i\]', '</em>', escaped, flags=re.IGNORECASE)

    # [u]...[/u]
    escaped = re.sub(r'\[u\]', '<u>', escaped, flags=re.IGNORECASE)
    escaped = re.sub(r'\[/u\]', '</u>', escaped, flags=re.IGNORECASE)

    # [s]...[/s]
    escaped = re.sub(r'\[s\]', '<s>', escaped, flags=re.IGNORECASE)
    escaped = re.sub(r'\[/s\]', '</s>', escaped, flags=re.IGNORECASE)

    return escaped
