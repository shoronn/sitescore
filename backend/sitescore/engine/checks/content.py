"""Content and accessibility: what visitors and Google find on the homepage itself."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..models import Category, Outcome, Status
from ..speedtest import accessibility as lighthouse_accessibility
from .base import check
from .performance import _failed, _source


async def _content(ctx):
    """(PageInfo, rendered) or an Outcome saying why the page could not be read."""
    page = await ctx.main_page()
    info, rendered = await ctx.content_info()
    if info is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable" if not page.ok else "not_html"), False
    return info, rendered


# ---------------------------------------------------------------- headings


@check("headings", "Page headings", Category.CONTENT, 1)
async def check_headings(ctx) -> Outcome:
    info, rendered = await _content(ctx)
    if isinstance(info, Outcome):
        return info
    h1s = info.h1s
    ev = {"h1_count": len(h1s), "h1": (h1s[0] if h1s else "")[:120], "headings": len(info.headings),
          "rendered": rendered}
    if not h1s:
        return Outcome(Status.WARN, ev, "no_h1")
    if len(h1s) > 1:
        return Outcome(Status.WARN, ev, "many_h1")
    previous = 0
    for level, _text in info.headings:
        if previous and level > previous + 1:
            ev["skipped"] = f"H{previous} to H{level}"
            return Outcome(Status.WARN, ev, "skipped")
        previous = level
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- image descriptions


def _is_pixel(img: dict[str, str]) -> bool:
    return img.get("width", "").strip() in ("0", "1") or img.get("height", "").strip() in ("0", "1")


@check("image_alt", "Image descriptions", Category.CONTENT, 1)
async def check_image_alt(ctx) -> Outcome:
    info, rendered = await _content(ctx)
    if isinstance(info, Outcome):
        return info
    images = [i for i in info.images if not _is_pixel(i) and (i.get("src") or i.get("data-src") or i.get("srcset"))]
    missing = [i for i in images if "alt" not in i]
    names = []
    for img in missing[:3]:
        src = img.get("src") or img.get("data-src") or ""
        name = (urlsplit(src).path.rsplit("/", 1)[-1] or src) if not src.startswith("data:") else "inline image"
        names.append(name if len(name) <= 36 else name[:24] + "..." + name[-8:])
    ev = {"images": len(images), "missing_count": len(missing), "examples": names, "rendered": rendered}
    if not images:
        return Outcome(Status.PASS, ev, "no_images")
    if not missing:
        return Outcome(Status.PASS, ev, "ok")
    if len(missing) >= 3 and len(missing) > len(images) / 2:
        return Outcome(Status.FAIL, ev, "most_missing")
    return Outcome(Status.WARN, ev, "some_missing")


# ---------------------------------------------------------------- amount of text


@check("content_depth", "Amount of text", Category.CONTENT, 1)
async def check_content_depth(ctx) -> Outcome:
    info, rendered = await _content(ctx)
    if isinstance(info, Outcome):
        return info
    raw = await ctx.page_info()
    ev = {"words": info.words, "rendered": rendered}
    if not rendered and info.scripts and info.words < 80 and ctx.settings.render_pages:
        # Scripts build the page and our browser could not render it either.
        return Outcome(Status.WARN, ev, "script_only")
    if rendered and raw is not None and raw.words < 50:
        ev["raw_words"] = raw.words
        if info.words >= 200:
            return Outcome(Status.WARN, ev, "needs_scripts")
    if info.words < 50:
        return Outcome(Status.FAIL, ev, "very_thin")
    if info.words < 200:
        return Outcome(Status.WARN, ev, "thin")
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- contact details

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_PHONE_RES = (
    re.compile(r"\+\d{1,3}[\s.\-]?\(?\d{1,5}\)?(?:[\s.\-]?\d{2,5}){2,4}"),   # +880 1897 669234, +1 (555) 010-0000
    re.compile(r"(?<!\d)01[3-9]\d{2}[\s\-]?\d{6}(?!\d)"),                     # Bangladeshi mobile: 01897-669234
    re.compile(r"\(\d{3}\)\s?\d{3}[\s.\-]\d{4}"),                              # (555) 010-0000
    re.compile(r"(?<!\d)0\d{2,4}[\s\-]\d{3,4}[\s\-]?\d{3,4}(?!\d)"),         # 020 7946 0000
)
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[a-z]{2,}", re.I)
_NOT_EMAIL = re.compile(r"\.(png|jpe?g|gif|svg|webp|avif)$", re.I)


def find_contacts(info) -> list[str]:
    """Which ways to get in touch the homepage shows: phone, email, WhatsApp, contact page."""
    found: list[str] = []
    hrefs = [h.lower() for h in info.anchors]
    text = info.text.translate(_BN_DIGITS)
    if any(h.startswith("tel:") for h in hrefs) or any(r.search(text) for r in _PHONE_RES):
        found.append("phone")
    emails = [e for e in _EMAIL_RE.findall(text) if not _NOT_EMAIL.search(e)]
    if any(h.startswith("mailto:") for h in hrefs) or emails:
        found.append("email")
    if any("wa.me/" in h or "whatsapp.com/send" in h or h.startswith("whatsapp:") for h in hrefs):
        found.append("WhatsApp")
    if any(re.search(r"contact|যোগাযোগ", h) for h in hrefs):
        found.append("contact page")
    return found


@check("contact_info", "Contact details", Category.CONTENT, 1)
async def check_contact_info(ctx) -> Outcome:
    info, rendered = await _content(ctx)
    if isinstance(info, Outcome):
        return info
    found = find_contacts(info)
    ev = {"found": found, "rendered": rendered}
    direct = [f for f in found if f != "contact page"]
    if direct:
        return Outcome(Status.PASS, ev, "ok")
    if found:
        return Outcome(Status.WARN, ev, "contact_page_only")
    return Outcome(Status.WARN, ev, "none")


# ---------------------------------------------------------------- page basics


@check("page_basics", "Page basics", Category.CONTENT, 1)
async def check_page_basics(ctx) -> Outcome:
    page = await ctx.main_page()
    info = await ctx.page_info()
    if info is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable" if not page.ok else "not_html")
    charset = "charset=" in (page.header("content-type") or "").lower() or any(
        "charset" in m or (m.get("http-equiv", "").lower() == "content-type" and "charset" in m.get("content", "").lower())
        for m in info.metas)
    checks = {"language": bool((info.lang or "").strip()), "character set": charset, "doctype": info.doctype}
    missing = [k for k, ok in checks.items() if not ok]
    ev = {"lang": (info.lang or "")[:20], "missing": missing}
    if missing:
        return Outcome(Status.WARN, ev, "missing")
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- accessibility (from the speed test)


@check("accessibility", "Accessibility", Category.CONTENT, 3, slow=True)
async def check_accessibility(ctx) -> Outcome:
    data = await ctx.speed_test()
    if "lhr" not in data:
        return _failed(data)
    a = lighthouse_accessibility(data["lhr"])
    if not a:
        return Outcome(Status.NOT_CHECKED, {}, "speed_failed")
    ev = _source(data, dict(a))
    if a["score"] >= 90:
        return Outcome(Status.PASS, ev, "ok" if not a["issues"] else "minor")
    if a["score"] >= 70:
        return Outcome(Status.WARN, ev, "some_issues")
    return Outcome(Status.FAIL, ev, "many_issues")
