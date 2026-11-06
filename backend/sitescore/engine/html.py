"""Small, forgiving HTML reader for the homepage checks (title, meta tags, links, headings, text)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Text inside these never shows on the page.
_INLINE = {"b", "i", "em", "strong", "span", "small", "u", "mark", "sup", "sub", "abbr", "code"}
_HIDDEN = {"script", "style", "noscript", "template", "svg", "head", "title"}

# Tags whose URL attribute loads something into the page, and how serious it is to load it
# over plain HTTP on an HTTPS page. "active" content (scripts, styles, frames, form targets)
# can change the page; browsers block it. "passive" content (images, media) only shows.
_RESOURCE_ATTRS = {
    "script": ("src", "active"),
    "iframe": ("src", "active"),
    "frame": ("src", "active"),
    "embed": ("src", "active"),
    "object": ("data", "active"),
    "form": ("action", "active"),
    "img": ("src", "passive"),
    "audio": ("src", "passive"),
    "video": ("src", "passive"),
    "source": ("src", "passive"),
    "track": ("src", "passive"),
}


@dataclass
class PageInfo:
    title: str | None = None
    lang: str | None = None
    metas: list[dict[str, str]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    resources: list[tuple[str, str, str]] = field(default_factory=list)  # (tag, url, active|passive)
    doctype: bool = False
    headings: list[tuple[int, str]] = field(default_factory=list)  # (level, text) in page order
    images: list[dict[str, str]] = field(default_factory=list)  # attributes of each <img>
    jsonld: list[str] = field(default_factory=list)  # raw <script type="application/ld+json"> blocks
    microdata: list[str] = field(default_factory=list)  # itemtype URLs
    anchors: list[str] = field(default_factory=list)  # href of every <a>
    scripts: int = 0
    text: str = ""  # visible text, whitespace collapsed (capped)

    @property
    def h1s(self) -> list[str]:
        return [t for level, t in self.headings if level == 1]

    @property
    def words(self) -> int:
        return len(re.findall(r"\w+", self.text))

    def meta(self, *names: str) -> str | None:
        """Content of the first <meta name=...> or <meta property=...> matching one of `names`."""
        wanted = {n.lower() for n in names}
        for m in self.metas:
            key = (m.get("name") or m.get("property") or "").lower()
            if key in wanted and m.get("content") is not None:
                return m["content"].strip()
        return None

    def has_link_rel(self, *rels: str) -> bool:
        wanted = {r.lower() for r in rels}
        for link in self.links:
            if wanted & set((link.get("rel") or "").lower().split()):
                return True
        return False


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.info = PageInfo()
        self._in_title = False
        self._title_parts: list[str] = []
        self._in_svg = 0
        self._hidden = 0
        self._heading: tuple[int, list[str]] | None = None
        self._jsonld: list[str] | None = None
        self._text: list[str] = []
        self._text_len = 0

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype"):
            self.info.doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "svg":
            self._in_svg += 1
        if tag in _HIDDEN:
            self._hidden += 1
        if tag == "script":
            self.info.scripts += 1
            if a.get("type", "").lower().strip() == "application/ld+json":
                self._jsonld = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and not self._in_svg:
            self._heading = (int(tag[1]), [])
        elif tag == "img":
            self.info.images.append(a)
        elif tag == "a" and a.get("href"):
            self.info.anchors.append(a["href"].strip())
        if tag not in _INLINE:
            self._add_text(" ")
        if a.get("itemtype"):
            self.info.microdata.append(a["itemtype"])
        if tag == "html" and a.get("lang"):
            self.info.lang = a["lang"].strip()
        elif tag == "title" and not self._in_svg and self.info.title is None:
            self._in_title = True
        elif tag == "meta":
            self.info.metas.append(a)
        elif tag == "link":
            self.info.links.append(a)
            if "stylesheet" in a.get("rel", "").lower().split() and a.get("href"):
                self.info.resources.append(("link", a["href"].strip(), "active"))
        if tag in _RESOURCE_ATTRS:
            attr, kind = _RESOURCE_ATTRS[tag]
            if a.get(attr):
                self.info.resources.append((tag, a[attr].strip(), kind))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag == "svg":
            self._in_svg -= 1
        if tag in _HIDDEN and self._hidden:
            self._hidden -= 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg" and self._in_svg:
            self._in_svg -= 1
        if tag in _HIDDEN and self._hidden:
            self._hidden -= 1
        if tag not in _INLINE:
            self._add_text(" ")
        if tag == "script" and self._jsonld is not None:
            self.info.jsonld.append("".join(self._jsonld))
            self._jsonld = None
        if self._heading and tag == f"h{self._heading[0]}":
            self.info.headings.append((self._heading[0], " ".join("".join(self._heading[1]).split())[:200]))
            self._heading = None
        if tag == "title" and self._in_title:
            self._in_title = False
            self.info.title = " ".join("".join(self._title_parts).split())

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._jsonld is not None:
            self._jsonld.append(data)
        if self._heading:
            self._heading[1].append(data)
        if not self._hidden:
            self._add_text(data)

    def _add_text(self, data: str) -> None:
        if self._text_len < 200_000:
            self._text.append(data)
            self._text_len += len(data)


def parse_page(html: str) -> PageInfo:
    reader = _Reader()
    try:
        reader.feed(html[:600_000])
        reader.close()
    except Exception:  # noqa: BLE001 - broken markup must never break a scan
        pass
    if reader._in_title and reader.info.title is None:
        reader.info.title = " ".join("".join(reader._title_parts).split())
    reader.info.text = " ".join("".join(reader._text).split())
    return reader.info
