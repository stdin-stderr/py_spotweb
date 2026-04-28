"""Build Newznab-compatible XML responses."""

from __future__ import annotations

from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring

from src.scanner.categories import spotnet_to_newznab_categories, spotnet_category_path

NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"

CATEGORIES = [
    (1000, "Console"),
    (1010, "Console/NDS"),
    (1020, "Console/PSP"),
    (1030, "Console/Wii"),
    (1040, "Console/Xbox"),
    (1050, "Console/Xbox 360"),
    (1080, "Console/PS3"),
    (2000, "Movies"),
    (2030, "Movies/SD"),
    (2040, "Movies/HD"),
    (2050, "Movies/BluRay"),
    (2060, "Movies/3D"),
    (3000, "Audio"),
    (3010, "Audio/MP3"),
    (3020, "Audio/Video"),
    (3040, "Audio/Lossless"),
    (4000, "PC"),
    (4020, "PC/Windows"),
    (4030, "PC/Mac"),
    (4040, "PC/Mobile"),
    (4050, "PC/Games"),
    (5000, "TV"),
    (5020, "TV/Foreign"),
    (5030, "TV/SD"),
    (5040, "TV/HD"),
    (5050, "TV/Other"),
    (5060, "TV/Sport"),
    (5070, "TV/Anime"),
    (6000, "XXX"),
    (6010, "XXX/DVD"),
    (6020, "XXX/WMV"),
    (6030, "XXX/XviD"),
    (6040, "XXX/x264"),
    (7000, "Other"),
    (7010, "Other/Misc"),
    (7020, "Other/Ebook"),
]

# Internal category_id → Newznab category id
# Internal IDs: 3=Audio, 4=Other, 5=Ebook, 6=PC/Apps, 7=XXX,
#               10=Movies HD, 11=Movies SD, 20=TV HD, 21=TV SD,
#               30=MP3, 31=Lossless
NEWZNAB_ID_MAP = {
    3: 3000, 4: 7000, 5: 7020, 6: 4000, 7: 6000,
    10: 2040, 11: 2030, 20: 5040, 21: 5030, 30: 3010, 31: 3040,
}


def _rss_root(title: str, base_url: str) -> tuple[Element, Element]:
    rss = Element("rss", version="2.0")
    rss.set("xmlns:newznab", NEWZNAB_NS)
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = base_url
    SubElement(channel, "description").text = "Usenet Indexer"
    return rss, channel


def caps_response(base_url: str) -> bytes:
    root = Element("caps")
    server = SubElement(root, "server")
    server.set("version", "1.0")
    server.set("title", "usenet-indexer")
    server.set("strapline", "Self-hosted Usenet indexer")
    server.set("url", base_url)

    limits = SubElement(root, "limits")
    limits.set("max", "100")
    limits.set("default", "50")

    searching = SubElement(root, "searching")
    SubElement(searching, "search", available="yes", supportedParams="q,limit,offset,cat,maxage")
    SubElement(searching, "tv-search", available="yes", supportedParams="q,season,ep,limit,offset,cat,maxage")
    SubElement(searching, "movie-search", available="yes", supportedParams="q,imdbid,limit,offset,cat,maxage")
    SubElement(searching, "audio-search", available="yes", supportedParams="q,limit,offset,cat,maxage")

    cats_el = SubElement(root, "categories")
    top_level = {cid: name for cid, name in CATEGORIES if cid % 1000 == 0}
    for cid, name in top_level.items():
        cat_el = SubElement(cats_el, "category", id=str(cid), name=name)
        for sub_cid, sub_name in CATEGORIES:
            if sub_cid // 1000 == cid // 1000 and sub_cid != cid:
                SubElement(cat_el, "subcat", id=str(sub_cid), name=sub_name.split("/", 1)[-1])

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode").encode()


def _newznab_attr(parent: Element, name: str, value: str) -> None:
    el = SubElement(parent, "newznab:attr")
    el.set("name", name)
    el.set("value", value)


def _format_date(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def search_response(releases: list[dict], base_url: str, total: int = 0) -> bytes:
    rss, channel = _rss_root("Search Results", base_url)
    response_el = SubElement(channel, "newznab:response")
    response_el.set("offset", "0")
    response_el.set("total", str(total or len(releases)))

    for rel in releases:
        item = SubElement(channel, "item")
        # Use messageid as canonical identifier, fall back to integer id
        rid = rel.get("messageid") or str(rel["id"])
        title = rel.get("title") or ""
        SubElement(item, "title").text = title
        SubElement(item, "guid").text = rid
        SubElement(item, "link").text = f"{base_url}/api?t=get&id={rid}"
        SubElement(item, "pubDate").text = _format_date(rel.get("posted_at"))

        nzb_url = f"{base_url}/api?t=get&id={rid}"
        has_image = rel.get("has_image")
        cover_url = f"{base_url}/image/{rid}" if has_image else ""
        desc_text = rel.get("description") or ""

        if cover_url:
            SubElement(item, "description").text = (
                f'<a href="{nzb_url}"><img src="{cover_url}"/></a> {desc_text}'
            )
        else:
            SubElement(item, "description").text = desc_text or title

        enc = SubElement(item, "enclosure")
        enc.set("url", nzb_url)
        enc.set("length", str(rel.get("total_bytes") or 0))
        enc.set("type", "application/x-nzb")

        # Determine categories from spotnet metadata if available
        spotnet_hcat = rel.get("spotnet_category")
        spotnet_subcats = rel.get("spotnet_subcats") or ""

        if spotnet_hcat is not None:
            # Use spotnet categories to get Newznab IDs
            newznab_cats = spotnet_to_newznab_categories(spotnet_hcat, spotnet_subcats)
            cat_path = spotnet_category_path(spotnet_hcat, spotnet_subcats)
            SubElement(item, "category").text = cat_path
        else:
            # Fallback to internal category_id if spotnet metadata missing
            newznab_cats = [NEWZNAB_ID_MAP.get(rel.get("category_id", 4), 7000)]

        for cat_id in newznab_cats:
            _newznab_attr(item, "category", str(cat_id))

        _newznab_attr(item, "size", str(rel.get("total_bytes") or 0))
        _newznab_attr(item, "files", str(rel.get("file_count") or 0))
        _newznab_attr(item, "poster", rel.get("poster") or "")
        _newznab_attr(item, "grabs", "0")
        _newznab_attr(item, "usenetdate", _format_date(rel.get("posted_at")))
        if cover_url:
            _newznab_attr(item, "coverurl", cover_url)

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode").encode()
