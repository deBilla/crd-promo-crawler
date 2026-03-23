# Security Checklist for Web Crawlers

A focused security reference for reviewing ContextCrawler code. These are the most common and impactful security issues in crawler implementations.

## Table of Contents

1. [SSRF (Server-Side Request Forgery)](#ssrf)
2. [Path Traversal](#path-traversal)
3. [Content Injection](#content-injection)
4. [Credential Leakage](#credential-leakage)
5. [Resource Exhaustion / DoS](#resource-exhaustion)
6. [DNS Rebinding](#dns-rebinding)
7. [Dependency Vulnerabilities](#dependencies)

---

## SSRF (Server-Side Request Forgery) <a id="ssrf"></a>

**Risk**: A malicious website can redirect the crawler to internal services (e.g., `http://169.254.169.254/` for cloud metadata, `http://localhost:6379/` for Redis).

**What to check**:
- Are redirect targets validated?
- Is the resolved IP checked against private ranges?
- Does the check happen *after* DNS resolution (not just hostname matching)?

**Private IP ranges to block**:
- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`
- `127.0.0.0/8`
- `169.254.0.0/16` (link-local / cloud metadata)
- `::1/128`, `fc00::/7`, `fe80::/10` (IPv6 private/link-local)

**Mitigation**: Validate the resolved IP *before* making the request, and validate again after redirect.

---

## Path Traversal <a id="path-traversal"></a>

**Risk**: When saving crawled content to disk using the URL path, a crafted URL like `https://evil.com/../../etc/passwd` could write outside the intended directory.

**What to check**:
- Are filenames derived from URLs sanitized?
- Is the final write path verified to be within the output directory?
- Are null bytes stripped from filenames?

**Mitigation**:
```python
from pathlib import Path

def safe_filepath(output_dir: Path, url_path: str) -> Path:
    # Sanitize: remove path traversal, null bytes, and special chars
    safe_name = url_path.replace("..", "").replace("\x00", "")
    safe_name = safe_name.strip("/").replace("/", "_")
    filepath = (output_dir / safe_name).resolve()
    # Verify it's still inside output_dir
    if not str(filepath).startswith(str(output_dir.resolve())):
        raise ValueError(f"Path traversal detected: {url_path}")
    return filepath
```

---

## Content Injection <a id="content-injection"></a>

**Risk**: Crawled content injected into logs, reports, or databases without sanitization could lead to log injection, XSS (if content is displayed in a web UI), or SQL injection (if stored in a database).

**What to check**:
- Are crawled strings sanitized before logging?
- Is user-controlled content parameterized in database queries?
- Are HTML reports of crawl results escaping crawled content?

---

## Credential Leakage <a id="credential-leakage"></a>

**Risk**: If the crawler sends authentication headers (e.g., API keys, cookies) to every domain it visits, a malicious redirect could steal credentials.

**What to check**:
- Are `Authorization` headers scoped to specific domains?
- Does httpx's redirect handling strip sensitive headers on cross-origin redirects? (By default it does, but custom code might not.)
- Are cookies isolated per domain?

---

## Resource Exhaustion / DoS <a id="resource-exhaustion"></a>

**Risk**: A malicious site can serve infinite content (e.g., `Content-Length: 999999999999`), infinite redirects, or dynamically generated infinite pages (spider traps).

**What to check**:
- Is there a maximum response size limit?
- Is there a redirect limit?
- Is there a maximum number of URLs per domain?
- Are there protections against spider traps (infinite URL patterns)?

**Common spider traps**:
- Calendar URLs: `/calendar/2025/01/01`, `/calendar/2025/01/02`, ...
- Session IDs in URLs: `/page?sid=abc123`, `/page?sid=def456`, ...
- Sorting/filtering: `/products?sort=price&order=asc&page=1`, ...

---

## DNS Rebinding <a id="dns-rebinding"></a>

**Risk**: Attacker's domain resolves to a public IP on first lookup, then to a private IP on the next. If the crawler validates the hostname but connects after a second DNS lookup, it can be tricked into accessing internal services.

**What to check**:
- Is IP validation done after DNS resolution, at connection time?
- Are DNS results cached to prevent rebinding between checks?

---

## Dependency Vulnerabilities <a id="dependencies"></a>

**What to check**:
- Are dependencies pinned to specific versions?
- Run `pip audit` or `safety check` periodically
- Key dependencies to watch: `httpx`, `lxml`, `beautifulsoup4`, `pydantic`
