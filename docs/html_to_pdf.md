## HTML to PDF (Playwright)

Asynchronous HTML-to-PDF generator using Playwright Chromium.

### Installation

Playwright is installed automatically through Python dependencies. Install Chromium separately:

```bash
# Windows / macOS
python -m playwright install --only-shell chromium

# Ubuntu / Debian
python -m playwright install --with-deps --only-shell chromium

# Verify installation
python -m playwright install --list
```

### Features

- Fast asynchronous PDF generation
- Automatic Chromium startup and browser reuse
- Automatic shutdown after 60 seconds of inactivity
- Up to 4 concurrent PDF requests per process
- HTML strings, local files, and remote URLs
- Custom page size, orientation, margins, and CSS page breaks
- Direct PDF response with optional file saving

### Usage

**Generate from HTML:**

```python
return await HTMLToPDF.from_text(
    html_text=html_content,
    filename="report.pdf",
    page_size="A4",
)
```

**Save PDF and return response:**

```python
return await HTMLToPDF.from_text(
    html_text=html_content,
    file_path="/app/generated/report.pdf",
    filename="report.pdf",
)
```

**Generate from local file or remote URL:**

```python
return await HTMLToPDF.from_url(
    url="/app/templates/report.html",
    filename="report.pdf",
)

return await HTMLToPDF.from_url(
    url="https://example.com/report",
    filename="report.pdf",
)
```

### CSS Page Configuration

```css
@page {
    size: A4;
    margin: 10mm;
}

.page-break {
    break-before: page;
}

.avoid-break {
    break-inside: avoid;
}
```

CSS-defined page sizes take priority over the Python `page_size` fallback.

### Configuration

```python
HTMLToPDF.IDLE_TIMEOUT = 60
```

The concurrent request limit defaults to 4 and is configured when the semaphore is initialized.

### Notes

- Chromium starts automatically on the first PDF request.
- Frequent requests reuse the existing browser.
- Chromium closes automatically after 60 seconds without active requests.
- No manual startup or shutdown calls are required during normal operation.
- Output directories must exist before saving PDFs.
- Use trusted HTML and URLs; restrict user-supplied sources in production.
- Chromium cleanup is best-effort if the application process terminates unexpectedly.
