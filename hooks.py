"""MkDocs hooks for agentrelay documentation."""


def on_page_content(html, page, **_):
    """Wrap API pages in a marker div for CSS scoping."""
    if page.file.src_path.startswith("api/"):
        return f'<div class="api-page">{html}</div>'
    return html
