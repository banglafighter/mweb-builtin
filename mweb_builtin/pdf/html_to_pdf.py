import asyncio
import logging
import os
import re
import sys
import tempfile
import platform
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import url2pathname

from mw_common import Console
from mweb import MWebResponse
from mweb_crud.common import MWebCRUDException


if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright


class HTMLToPDF:

    IDLE_TIMEOUT = 60
    MAX_CONCURRENT = 4

    _playwright: "Playwright | None" = None
    _browser: "Browser | None" = None

    _active_requests = 0
    _lock = asyncio.Lock()
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    _idle_handle = None

    @classmethod
    async def _install_chromium(cls):
        command = [
            sys.executable,
            "-m",
            "playwright",
            "install",
        ]

        if platform.system() == "Linux":
            command.append("--with-deps")

        command.extend([
            "--only-shell",
            "chromium",
        ])

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            output, _ = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.communicate()

            raise

        if process.returncode != 0:
            message = output.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Chromium installation failed:\n{message}"
            )

        Console.info("Chromium installed successfully")

    @classmethod
    async def _start(cls):
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. "
                "Install the declared mweb-builtin dependencies "
                "using your project dependency updater."
            ) from exc

        async with cls._lock:
            if cls._browser and cls._browser.is_connected():
                return cls._browser

            if cls._playwright:
                try:
                    await cls._playwright.stop()
                finally:
                    cls._playwright = None
                    cls._browser = None

            playwright = await async_playwright().start()

            try:
                executable = Path(
                    playwright.chromium.executable_path
                )

                if not executable.is_file():
                    await cls._install_chromium()

                browser = await playwright.chromium.launch(
                    headless=True,
                )

            except BaseException:
                await playwright.stop()
                raise

            cls._playwright = playwright
            cls._browser = browser

            return browser

    @classmethod
    async def _close_if_idle(cls):
        async with cls._lock:
            if cls._active_requests > 0:
                return

            browser = cls._browser
            playwright = cls._playwright

            cls._browser = None
            cls._playwright = None

            try:
                if browser:
                    await browser.close()
            finally:
                if playwright:
                    await playwright.stop()

    @classmethod
    async def _idle_shutdown(cls):
        try:
            await cls._close_if_idle()
        except Exception:
            Console.log("Failed to close idle Chromium browser")

    @classmethod
    async def _begin_request(cls):
        async with cls._lock:
            if cls._idle_handle is not None:
                cls._idle_handle.cancel()
                cls._idle_handle = None

            cls._active_requests += 1

    @classmethod
    async def _end_request(cls):
        async with cls._lock:
            cls._active_requests -= 1

            if cls._active_requests == 0:
                loop = asyncio.get_running_loop()

                cls._idle_handle = loop.call_later(
                    cls.IDLE_TIMEOUT,
                    lambda: asyncio.create_task(
                        cls._idle_shutdown()
                    ),
                )

    @classmethod
    def _resolve_url(cls, url: str | Path):
        if isinstance(url, Path):
            return url.resolve().as_uri()

        value = str(url).strip()

        if not value:
            raise MWebCRUDException(
                message="Invalid PDF source URL"
            )

        if value.startswith(("http://", "https://")):
            parsed = urlsplit(value)

            if not parsed.netloc:
                raise MWebCRUDException(
                    message="Invalid PDF source URL"
                )

            return value

        if value.startswith("file://"):
            return value

        if "://" in value:
            raise MWebCRUDException(
                message="Unsupported PDF source URL"
            )

        return Path(value).resolve().as_uri()

    @classmethod
    def _get_local_path(cls, value: str | Path):
        if isinstance(value, Path):
            return value.resolve()

        source = str(value)

        if source.startswith("file://"):
            parsed = urlsplit(source)

            if parsed.netloc not in ("", "localhost"):
                raise MWebCRUDException(
                    message="Unsupported local file URL"
                )

            return Path(
                url2pathname(parsed.path)
            ).resolve()

        return Path(source).resolve()

    @classmethod
    def _prepare_html(cls, html_text: str, base_url: str):
        base_tag = f'<base href="{escape(base_url, quote=True)}">'

        head_pattern = r"<head(?:\s[^>]*)?>"
        html_pattern = r"<html(?:\s[^>]*)?>"

        if re.search(head_pattern, html_text, re.IGNORECASE):
            return re.sub(
                head_pattern,
                lambda match: match.group(0) + base_tag,
                html_text,
                count=1,
                flags=re.IGNORECASE,
            )

        if re.search(html_pattern, html_text, re.IGNORECASE):
            return re.sub(
                html_pattern,
                lambda match: (
                    match.group(0)
                    + "<head>"
                    + base_tag
                    + "</head>"
                ),
                html_text,
                count=1,
                flags=re.IGNORECASE,
            )

        return "<head>" + base_tag + "</head>" + html_text

    @classmethod
    def _write_temporary_html(cls, html_text: str, directory: Path):
        fd, name = tempfile.mkstemp(
            suffix=".html",
            prefix=".pdf-",
            dir=directory,
        )

        file_path = Path(name)

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(html_text)

            return file_path

        except BaseException:
            file_path.unlink(missing_ok=True)
            raise

    @classmethod
    async def _load_content(cls, page, html_text: str | None, url: str | Path | None, base_url: str | Path | None, timeout: int):
        if url is not None:
            target_url = cls._resolve_url(url)

            response = await page.goto(
                target_url,
                wait_until="load",
                timeout=timeout,
            )

            if response and response.status >= 400:
                raise MWebCRUDException(
                    message=f"PDF source returned HTTP {response.status}"
                )

            return None

        if base_url is None:
            await page.set_content(
                html_text,
                wait_until="load",
                timeout=timeout,
            )

            return None

        resolved_url = cls._resolve_url(base_url)

        if resolved_url.startswith(("http://", "https://")):
            if str(base_url).endswith("/"):
                resolved_url = resolved_url.rstrip("/") + "/"

            content = cls._prepare_html(
                html_text=html_text,
                base_url=resolved_url,
            )

            await page.set_content(
                content,
                wait_until="load",
                timeout=timeout,
            )

            return None

        local_path = cls._get_local_path(base_url)

        if local_path.is_dir():
            directory = local_path
        elif local_path.is_file():
            directory = local_path.parent
        else:
            raise MWebCRUDException(
                message=f"Invalid local base URL: {base_url}"
            )

        temporary_file = await asyncio.to_thread(
            cls._write_temporary_html,
            html_text,
            directory,
        )

        try:
            await page.goto(
                temporary_file.as_uri(),
                wait_until="load",
                timeout=timeout,
            )

            return temporary_file

        except BaseException:
            await asyncio.to_thread(
                temporary_file.unlink,
                missing_ok=True,
            )
            raise

    @classmethod
    async def _generate(cls, html_text: str | None = None, url: str | Path | None = None, base_url: str | Path | None = None, page_size: str = "A4", landscape: bool = False, margin: str = "0", wait_for: str | None = None, timeout: int = 60000):
        if html_text is None and url is None:
            raise MWebCRUDException(
                message="Invalid pdf content"
            )

        if timeout <= 0:
            raise ValueError(
                "timeout must be greater than zero"
            )

        await cls._begin_request()

        try:
            async with cls._semaphore:
                browser = await cls._start()

                context = await browser.new_context(
                    accept_downloads=False,
                )

                temporary_file = None

                try:
                    context.set_default_timeout(timeout)
                    context.set_default_navigation_timeout(timeout)

                    page = await context.new_page()

                    temporary_file = await cls._load_content(
                        page=page,
                        html_text=html_text,
                        url=url,
                        base_url=base_url,
                        timeout=timeout,
                    )

                    if wait_for:
                        await page.locator(wait_for).wait_for(
                            state="visible",
                            timeout=timeout,
                        )

                    await asyncio.wait_for(
                        page.evaluate("document.fonts.ready"),
                        timeout=timeout / 1000,
                    )

                    pdf_bytes = await asyncio.wait_for(
                        page.pdf(
                            format=page_size,
                            landscape=landscape,
                            margin={
                                "top": margin,
                                "right": margin,
                                "bottom": margin,
                                "left": margin,
                            },
                            print_background=True,
                            prefer_css_page_size=True,
                        ),
                        timeout=timeout / 1000,
                    )

                    return pdf_bytes

                finally:
                    try:
                        await context.close()
                    finally:
                        if temporary_file:
                            await asyncio.to_thread(
                                temporary_file.unlink,
                                missing_ok=True,
                            )

        finally:
            await cls._end_request()

    @classmethod
    async def _response(cls, pdf_bytes: bytes, file_path: str | Path | None = None, filename: str | None = None):
        if file_path is not None:
            await asyncio.to_thread(
                Path(file_path).write_bytes,
                pdf_bytes,
            )

        return await MWebResponse.response_pdf(
            bytes_content=pdf_bytes,
            filename=filename,
        )

    @classmethod
    async def from_text(cls, html_text: str, file_path: str | Path | None = None, filename: str | None = None, base_url: str | Path | None = None, page_size: str = "A4", landscape: bool = False, margin: str = "0", wait_for: str | None = None, timeout: int = 60000):
        if not html_text:
            raise MWebCRUDException(
                message="Invalid pdf content"
            )

        pdf_bytes = await cls._generate(
            html_text=html_text,
            base_url=base_url,
            page_size=page_size,
            landscape=landscape,
            margin=margin,
            wait_for=wait_for,
            timeout=timeout,
        )

        return await cls._response(
            pdf_bytes=pdf_bytes,
            file_path=file_path,
            filename=filename,
        )

    @classmethod
    async def from_url(cls, url: str | Path, file_path: str | Path | None = None, filename: str | None = None, page_size: str = "A4", landscape: bool = False, margin: str = "0", wait_for: str | None = None, timeout: int = 60000):
        pdf_bytes = await cls._generate(
            url=url,
            page_size=page_size,
            landscape=landscape,
            margin=margin,
            wait_for=wait_for,
            timeout=timeout,
        )

        return await cls._response(
            pdf_bytes=pdf_bytes,
            file_path=file_path,
            filename=filename,
        )
