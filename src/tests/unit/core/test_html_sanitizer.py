import pytest

from core.utils.html_sanitizer import sanitize_description_html


@pytest.mark.unit
class TestHTMLSanitizer:
    def test_none_and_empty_returns_none(self):
        assert sanitize_description_html(None) is None
        assert sanitize_description_html("") is None
        assert sanitize_description_html("   \n\t  ") is None
        assert sanitize_description_html("<p></p>") is None
        assert sanitize_description_html("<p><br></p>") is None
        assert sanitize_description_html("<div>   </div>") is None
        assert sanitize_description_html("<h3></h3>") is None
        assert sanitize_description_html("<ul><li></li></ul>") is None

    def test_plain_text_normalization(self):
        assert sanitize_description_html("Single line text") == "<p>Single line text</p>"
        assert sanitize_description_html("Paragraph 1\n\nParagraph 2") == "<p>Paragraph 1</p><p>Paragraph 2</p>"
        assert sanitize_description_html("Line 1\nLine 2\n\nLine 3") == "<p>Line 1<br>Line 2</p><p>Line 3</p>"
        assert (
            sanitize_description_html("Text with & ampersand and 1 < 2 comparisons")
            == "<p>Text with &amp; ampersand and 1 &lt; 2 comparisons</p>"
        )

    def test_allowed_tags_preserved_attributes_stripped(self):
        html_input = (
            '<h3 class="title" style="color: red;">Header</h3>'
            '<p id="p1" onclick="alert(1)">This is <strong>strong</strong>, <em>emphasized</em> text.<br></p>'
            '<ul class="list"><li data-id="1">Item 1</li><li>Item 2</li></ul>'
            "<ol><li>First</li><li>Second</li></ol>"
        )
        expected = (
            "<h3>Header</h3>"
            "<p>This is <strong>strong</strong>, <em>emphasized</em> text.<br></p>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
            "<ol><li>First</li><li>Second</li></ol>"
        )
        assert sanitize_description_html(html_input) == expected

    def test_tag_mappings(self):
        html_input = "<h1>Title 1</h1><h2>Title 2</h2><p><b>Bold</b> and <i>Italic</i></p>"
        expected = "<h3>Title 1</h3><h3>Title 2</h3><p><strong>Bold</strong> and <em>Italic</em></p>"
        assert sanitize_description_html(html_input) == expected

    def test_dangerous_tags_and_content_dropped(self):
        html_input = (
            "<p>Safe text</p>"
            "<script>alert('xss');</script>"
            "<style>body { display: none; }</style>"
            "<iframe src='https://evil.com'></iframe>"
            "<object data='evil.swf'></object>"
            "<p>More safe text</p>"
        )
        expected = "<p>Safe text</p><p>More safe text</p>"
        assert sanitize_description_html(html_input) == expected

    def test_disallowed_containers_stripped_content_retained(self):
        html_input = '<div><span class="highlight">Inline text in a span</span> and <a href="https://example.com">link text</a></div>'
        expected = "<p>Inline text in a span and link text</p>"
        assert sanitize_description_html(html_input) == expected

    def test_unclosed_tags_auto_closed(self):
        html_input = "<h3>Header<p>Paragraph with <strong>bold"
        sanitized = sanitize_description_html(html_input)
        assert sanitized == "<h3>Header</h3><p>Paragraph with <strong>bold</strong></p>"
