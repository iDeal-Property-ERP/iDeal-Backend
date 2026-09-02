"""Canonical restricted HTML sanitizer and plain-text normalizer for listing descriptions."""

import html
import re
from html.parser import HTMLParser

ALLOWED_TAGS = {"p", "br", "strong", "em", "h3", "ul", "ol", "li"}

TAG_MAPPING = {
    "b": "strong",
    "i": "em",
    "h1": "h3",
    "h2": "h3",
    "h4": "h3",
    "h5": "h3",
    "h6": "h3",
}

DROP_CONTENT_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "applet",
    "form",
    "svg",
    "canvas",
    "template",
    "noscript",
    "head",
    "meta",
    "link",
}

# Block tags that cannot be nested inside each other (or close preceding same-level tags)
HEADING_AND_PARAGRAPH_TAGS = {"p", "h3"}


class _DescriptionHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.drop_stack: list[str] = []
        self.open_tags: list[str] = []

    def _close_tag(self, target_tag: str) -> None:
        while self.open_tags:
            top = self.open_tags.pop()
            self.output.append(f"</{top}>")
            if top == target_tag:
                break

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in DROP_CONTENT_TAGS:
            self.drop_stack.append(tag_lower)
            return

        if self.drop_stack:
            return

        mapped_tag = TAG_MAPPING.get(tag_lower, tag_lower)

        # Auto-close incompatible open tags
        if mapped_tag in HEADING_AND_PARAGRAPH_TAGS:
            if self.open_tags and self.open_tags[-1] in HEADING_AND_PARAGRAPH_TAGS:
                self._close_tag(self.open_tags[-1])
        elif mapped_tag == "li":
            if self.open_tags and self.open_tags[-1] == "li":
                self._close_tag("li")
        elif mapped_tag in {"ul", "ol"} and self.open_tags and self.open_tags[-1] in HEADING_AND_PARAGRAPH_TAGS:
            self._close_tag(self.open_tags[-1])

        if mapped_tag in ALLOWED_TAGS:
            if mapped_tag == "br":
                self.output.append("<br>")
            else:
                self.output.append(f"<{mapped_tag}>")
                self.open_tags.append(mapped_tag)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self.drop_stack:
            if tag_lower in DROP_CONTENT_TAGS:
                if self.drop_stack and self.drop_stack[-1] == tag_lower:
                    self.drop_stack.pop()
                elif tag_lower in self.drop_stack:
                    self.drop_stack.remove(tag_lower)
            return

        mapped_tag = TAG_MAPPING.get(tag_lower, tag_lower)
        if mapped_tag in ALLOWED_TAGS and mapped_tag != "br" and mapped_tag in self.open_tags:
            self._close_tag(mapped_tag)

    def handle_data(self, data: str) -> None:
        if self.drop_stack:
            return
        self.output.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self.drop_stack:
            return
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.drop_stack:
            return
        self.output.append(f"&#{name};")

    def get_sanitized_html(self) -> str:
        self.close()
        while self.open_tags:
            top = self.open_tags.pop()
            self.output.append(f"</{top}>")
        return "".join(self.output)


def sanitize_description_html(value: str | None) -> str | None:
    """Sanitize, normalize, and validate a description string to canonical restricted HTML.

    Rules:
    - None or empty/whitespace string -> None
    - Plain text (no HTML tags) -> wrap in <p> tags, convert newlines to <br>
    - HTML input -> sanitize to allowed tags (p, br, strong, em, h3, ul, ol, li) with NO attributes
    - Disallowed/dangerous tags (<script>, <iframe>, etc.) dropped with content
    - Empty content (e.g. '<p></p>', '<p><br></p>', only whitespace) -> None
    """
    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    # Check if input contains valid HTML tags (must be an actual known or html-formatted tag)
    # Match strings like <p>, </p>, <br/>, <span ...>, etc.
    has_html_tags = bool(re.search(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9]*(\s+[^>]*)?>", trimmed))

    if not has_html_tags:
        # Plain text conversion
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", trimmed) if p.strip()]
        if not paragraphs:
            return None
        formatted_paragraphs = []
        for p in paragraphs:
            escaped = html.escape(p, quote=False)
            with_br = re.sub(r"\r?\n", "<br>", escaped)
            formatted_paragraphs.append(f"<p>{with_br}</p>")
        result = "".join(formatted_paragraphs)
    else:
        parser = _DescriptionHTMLSanitizer()
        try:
            parser.feed(trimmed)
            result = parser.get_sanitized_html()
        except Exception:
            # Fallback on parse failure: treat as escaped plain text
            escaped = html.escape(trimmed, quote=False)
            result = f"<p>{escaped}</p>"

    # If result doesn't have top-level structural block tags (<p>, <h3>, <ul>, <ol>), wrap in <p>
    if result and not re.search(r"^<(p|h3|ul|ol)>", result.strip()):
        result = f"<p>{result}</p>"

    # Clean up empty tags like <p></p>, <h3></h3>, <li></li>
    result = re.sub(r"<(p|h3|strong|em|li)>\s*(<br>)?\s*</\1>", "", result)

    # Post-check: ensure there is meaningful visible text content
    plain_text_check = re.sub(r"<[^>]+>", "", result)
    plain_text_check = html.unescape(plain_text_check).replace("\xa0", " ").strip()
    if not plain_text_check:
        return None

    return result
