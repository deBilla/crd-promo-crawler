# HTML Test Fixtures Catalog

Store these in `tests/fixtures/html/`. Each fixture tests a specific parsing scenario.

## simple_page.html

Basic well-formed HTML page for happy-path tests:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Simple Test Page</title>
    <meta name="description" content="A simple test page for ContextCrawler">
</head>
<body>
    <h1>Welcome to the Test Page</h1>
    <p>This is a simple page with some text content.</p>
    <p>It has multiple paragraphs for content extraction testing.</p>
</body>
</html>
```

## with_links.html

Page with various link types for extraction testing:

```html
<!DOCTYPE html>
<html>
<head><title>Page With Links</title></head>
<body>
    <nav>
        <a href="https://example.com/absolute">Absolute Link</a>
        <a href="/relative-root">Root Relative</a>
        <a href="relative-path">Path Relative</a>
        <a href="../parent">Parent Path</a>
        <a href="https://other-domain.com/external">External Link</a>
    </nav>
    <main>
        <a href="https://example.com/page#section">With Fragment</a>
        <a href="https://example.com/page?key=value">With Query</a>
        <a href="mailto:test@example.com">Email Link</a>
        <a href="javascript:void(0)">JavaScript Link</a>
        <a href="tel:+1234567890">Phone Link</a>
        <a href="">Empty Href</a>
        <a>No Href At All</a>
    </main>
    <footer>
        <a href="https://example.com/page">Duplicate 1</a>
        <a href="https://example.com/page">Duplicate 2</a>
    </footer>
</body>
</html>
```

## malformed.html

Deliberately broken HTML to test parser resilience:

```html
<html>
<head><title>Broken Page</head>
<body>
    <p>Unclosed paragraph
    <a href="/link1">Link inside unclosed p
    <div>
        <a href="/link2">Nested link</a>
    </p>  <!-- Mismatched closing tag -->
    <a href='/link3' class=unquoted>Unquoted attribute</a>
    <a HREF="/link4">Uppercase attribute</a>
    <a href = " /link5 ">Spaces around URL</a>
    <br><br><br>
    <a href="/link6">Last link
</body>
```

## javascript_heavy.html

Page where content is loaded via JavaScript (tests extraction limits):

```html
<!DOCTYPE html>
<html>
<head><title>JS Heavy Page</title></head>
<body>
    <div id="app">Loading...</div>
    <script>
        document.getElementById('app').innerHTML = '<a href="/dynamic">Dynamic Link</a>';
    </script>
    <noscript>
        <a href="/fallback">Fallback Link</a>
    </noscript>
    <!-- Hidden links that some crawlers might find -->
    <a href="/visible" style="display:none">Hidden via CSS</a>
    <a href="/comment-link"><!-- This is a comment link --></a>
</body>
</html>
```

## pagination.html

Page with common pagination patterns:

```html
<!DOCTYPE html>
<html>
<head><title>Paginated Content</title></head>
<body>
    <div class="content">
        <article><h2>Article 1</h2><p>Content here.</p></article>
        <article><h2>Article 2</h2><p>More content.</p></article>
    </div>
    <nav class="pagination">
        <a href="/page/1" class="active">1</a>
        <a href="/page/2">2</a>
        <a href="/page/3">3</a>
        <a href="/page/2" rel="next">Next &raquo;</a>
        <a href="/page/10" rel="last">Last</a>
    </nav>
</body>
</html>
```

## structured_data.html

Page with JSON-LD and microdata for structured extraction:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Product Page</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Test Widget",
        "description": "A widget for testing",
        "price": "29.99",
        "currency": "USD"
    }
    </script>
</head>
<body>
    <div itemscope itemtype="https://schema.org/Product">
        <h1 itemprop="name">Test Widget</h1>
        <p itemprop="description">A widget for testing</p>
        <span itemprop="price">$29.99</span>
    </div>
</body>
</html>
```

## When to Use Each Fixture

| Fixture | Use For |
|---------|---------|
| `simple_page.html` | Basic content extraction, title/meta parsing |
| `with_links.html` | Link extractor tests, URL resolution, dedup |
| `malformed.html` | Parser resilience, error handling |
| `javascript_heavy.html` | Verifying static extraction limits |
| `pagination.html` | Next-page detection, crawl depth |
| `structured_data.html` | JSON-LD/microdata extraction |
