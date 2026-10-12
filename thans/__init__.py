"""THANS — fully offline voice & text file assistant."""

__version__ = "0.2.0"
APP_NAME = "THANS"
APP_TAGLINE = "Offline voice & text file assistant"


#: Characters we print that legacy code pages (Windows cp1252, cp850) cannot
#: encode — file listings use 📁/📄/🎤, the CLI banner uses “·”.
_GLYPH_SAMPLE = "📁📄✨♻️🎤·"


def use_utf8_output() -> None:
    """Keep stdout/stderr from crashing on legacy consoles.

    A redirected Windows stream defaults to the ANSI code page, so writing our
    📁/📄 listings raised ``UnicodeEncodeError`` and aborted the run. When (and
    only when) the current encoding cannot represent those glyphs, switch that
    stream to UTF-8 with ``errors="replace"``. Streams that already handle them
    (real consoles, UTF-8 locales, StringIO in tests) are left untouched.
    """
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            encoding = (getattr(stream, "encoding", "") or "").lower()
            if not encoding or encoding.replace("-", "").startswith("utf8"):
                continue
            _GLYPH_SAMPLE.encode(encoding)          # raises if unsupported
        except (UnicodeEncodeError, LookupError):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
            except Exception:
                pass
