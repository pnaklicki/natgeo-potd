"""Data coordinator for the National Geographic Photo of the Day.

The page parsing is based on the selectors used by the unofficial
Nat-Geo-Photo-of-the-Day-API by Sterling Whitley (MIT License):

- ``div.primary_photo img``       -> photo URL
- ``div#caption p:nth-child(4)``  -> description
- ``div#caption p.credit``        -> "Photograph by <name>"

Newer page layouts are handled with fallbacks: the caption credit, the embedded
``crdt`` field, JSON-LD and Open Graph meta tags.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PAGE_URL, REQUEST_TIMEOUT, UPDATE_INTERVAL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

META_TAG_RE = re.compile(r"<meta\s[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(r'([\w:.-]+)\s*=\s*"([^"]*)"')
JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
CAPTION_CREDIT_RE = re.compile(
    r'<span[^>]*class="[^"]*Caption__Credit[^"]*"[^>]*>([^<]+)</span>'
)
JSON_CREDIT_RE = re.compile(r'"crdt"\s*:\s*"([^"]+)"')
CREDIT_BY_RE = re.compile(r"Photograph(?:ed)?\s+by\s+([^,]+)", re.IGNORECASE)
SITE_SUFFIX_RE = re.compile(
    r"\s*\|\s*(Nat Geo Photo of the Day|National Geographic|Photo of the Day)\s*$",
    re.IGNORECASE,
)
# Site-wide names that must never be reported as the photographer.
GENERIC_AUTHORS = frozenset(
    {"national geographic", "natgeo", "nat geo", "national geographic society"}
)
VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }
)


@dataclass(frozen=True)
class NatGeoPhoto:
    """Today's photo of the day."""

    title: str | None
    description: str | None
    author: str | None
    page_url: str
    image_url: str
    image_bytes: bytes
    content_type: str
    fetched_at: datetime


class PhotoPageParser(HTMLParser):
    """Extract the photo URL, caption description and credit from the page HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[dict[str, Any]] = []
        self._capturing: dict[str, list[str]] = {}
        self.image_src: str | None = None
        self.description: str | None = None
        self.credit: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        parent = self._stack[-1] if self._stack else None
        if parent is not None:
            parent["children"] += 1
        classes = values.get("class", "").split()
        in_primary = any("primary_photo" in e["classes"] for e in self._stack)
        in_caption = any(e["id"] == "caption" for e in self._stack)

        if tag == "img":
            if in_primary and self.image_src is None:
                self.image_src = values.get("src") or values.get("data-src") or None
            return  # void element, nothing to push

        key = None
        if tag == "p" and in_caption:
            if (
                parent is not None
                and parent["id"] == "caption"
                and parent["children"] == 4
                and self.description is None
            ):
                key = "description"
            elif "credit" in classes and self.credit is None:
                key = "credit"

        if tag not in VOID_ELEMENTS:
            self._stack.append(
                {
                    "tag": tag,
                    "id": values.get("id", ""),
                    "classes": classes,
                    "children": 0,
                    "key": key,
                }
            )
            if key:
                self._capturing[key] = []

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                for element in self._stack[index:]:
                    self._finish(element)
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        for chunks in self._capturing.values():
            chunks.append(data)

    def _finish(self, element: dict[str, Any]) -> None:
        key = element["key"]
        if not key or key not in self._capturing:
            return
        text = " ".join("".join(self._capturing.pop(key)).split()) or None
        if key == "description":
            self.description = text
        elif key == "credit":
            self.credit = text


def _parse_meta(page: str) -> dict[str, str]:
    """Return meta tags (og:, twitter:, name=) keyed by lowercase property name."""
    meta: dict[str, str] = {}
    for tag in META_TAG_RE.findall(page):
        attrs = dict(ATTR_RE.findall(tag))
        key = attrs.get("property") or attrs.get("name")
        content = attrs.get("content")
        if key and content and key.lower() not in meta:
            meta[key.lower()] = html.unescape(content).strip()
    return meta


def _iter_json_ld(page: str) -> list[dict[str, Any]]:
    """Return every JSON-LD object on the page, flattening lists and @graph."""
    items: list[dict[str, Any]] = []

    def _collect(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                _collect(child)
        elif isinstance(node, dict):
            items.append(node)
            if "@graph" in node:
                _collect(node["@graph"])

    for raw in JSON_LD_RE.findall(page):
        try:
            _collect(json.loads(raw.strip()))
        except ValueError:
            continue
    return items


def _ld_value(items: list[dict[str, Any]], key: str) -> str | None:
    """Return the first non-empty string value for a JSON-LD key."""
    for item in items:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("name") or value.get("url")
        if isinstance(value, list) and value:
            first = value[0]
            value = first.get("name") if isinstance(first, dict) else first
        if isinstance(value, str) and value.strip():
            return html.unescape(value).strip()
    return None


def _clean_title(title: str | None) -> str | None:
    """Remove the site name that is appended to the photo title."""
    if not title:
        return None
    return SITE_SUFFIX_RE.sub("", title).strip() or title


def _clean_author(name: str | None) -> str | None:
    """Return the name, or None if it is empty or only the site name."""
    if not name:
        return None
    name = name.strip().lstrip("@").strip()
    if not name or name.lower() in GENERIC_AUTHORS or name.startswith("http"):
        return None
    return name


def _author_from_page(
    parser: PhotoPageParser, page: str, meta: dict[str, str], ld: list[dict[str, Any]]
) -> str | None:
    """Find the photographer, trying the most specific source first."""
    candidates: list[str | None] = []
    if parser.credit:
        match = CREDIT_BY_RE.search(parser.credit)
        candidates.append(match.group(1) if match else None)
    caption = CAPTION_CREDIT_RE.search(page)
    candidates.append(caption.group(1) if caption else None)
    embedded = JSON_CREDIT_RE.search(page)
    candidates.append(embedded.group(1) if embedded else None)
    candidates += [
        _ld_value(ld, "author"),
        _ld_value(ld, "creator"),
        meta.get("author"),
        meta.get("article:author"),
        meta.get("twitter:creator"),
    ]
    for candidate in candidates:
        name = _clean_author(html.unescape(candidate) if candidate else None)
        if name:
            return name
    return None


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device shared by all entities of this integration."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="National Geographic Photo of the Day",
        manufacturer="National Geographic",
        model="Photo of the Day",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=PAGE_URL,
    )


class NatGeoPhotoCoordinator(DataUpdateCoordinator[NatGeoPhoto]):
    """Polls the Photo of the Day page and downloads the image when it changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api_calls = 0
        self.api_errors = 0
        self.last_error: str | None = None

    async def _get(self, session: aiohttp.ClientSession, url: str) -> aiohttp.ClientResponse:
        self.api_calls += 1
        async with asyncio.timeout(REQUEST_TIMEOUT):
            response = await session.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response

    async def _async_update_data(self) -> NatGeoPhoto:
        session = async_get_clientsession(self.hass)
        previous = self.data

        try:
            resp = await self._get(session, PAGE_URL)
            try:
                page_html = await resp.text()
            finally:
                resp.release()

            meta = _parse_meta(page_html)
            ld = _iter_json_ld(page_html)
            parser = PhotoPageParser()
            parser.feed(page_html)
            parser.close()

            raw_image = meta.get("og:image") or _ld_value(ld, "image") or parser.image_src
            if not raw_image:
                raise ValueError("No image found on the Photo of the Day page")
            image_url = urljoin(PAGE_URL, raw_image)

            # Download the image only when the photo has changed.
            if previous and previous.image_url == image_url:
                image_bytes, content_type = previous.image_bytes, previous.content_type
            else:
                img = await self._get(session, image_url)
                try:
                    image_bytes = await img.read()
                    content_type = img.content_type or "image/jpeg"
                finally:
                    img.release()

        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            self.api_errors += 1
            self.last_error = str(err) or type(err).__name__
            _LOGGER.warning("Could not update photo of the day: %s", self.last_error)
            raise UpdateFailed(
                f"Failed to fetch photo of the day: {self.last_error}"
            ) from err

        self.last_error = None
        return NatGeoPhoto(
            title=_clean_title(meta.get("og:title") or _ld_value(ld, "headline")),
            description=(
                parser.description
                or meta.get("og:description")
                or _ld_value(ld, "description")
            ),
            author=_author_from_page(parser, page_html, meta, ld),
            page_url=meta.get("og:url", PAGE_URL),
            image_url=image_url,
            image_bytes=image_bytes,
            content_type=content_type,
            fetched_at=dt_util.utcnow(),
        )
