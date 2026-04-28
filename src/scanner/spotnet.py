"""Spotnet protocol support: parse free.pt article bodies and assemble NZB files.

Spotnet articles are XML documents posted to free.pt. The XML contains proper
release metadata (title, poster, category, size) and a list of segment message-IDs
that together form the NZB data. Each segment body uses Spotnet's custom escaping
(=C/=B/=A/=D) and is raw-deflate compressed; we unescape and inflate to get the NZB.
"""

from __future__ import annotations

import base64
import logging
import re
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Matches the raw SubCat XML format {digits}{letter}{digits}, e.g. "9a0" or "11b4"
_SUBCAT_RE = re.compile(r'(\d+)([aAbBcCdDzZ])(\d+)', re.IGNORECASE)

# Spotnet category code → internal category_id
# 0=video, 1=audio, 2=image/ebook, 3=applications
_CAT_VIDEO_MOVIE = 10   # Movies HD  (newznab 2040)
_CAT_VIDEO_TV    = 20   # TV HD      (newznab 5040)
_CAT_AUDIO       = 3    # Audio      (newznab 3000)
_CAT_IMAGE       = 5    # Ebook/Mag  (newznab 7020)
_CAT_PC          = 6    # PC/Apps    (newznab 4000)
_CAT_XXX         = 7    # XXX        (newznab 6000)
_CAT_OTHER       = 4    # Other      (newznab 7000)


@dataclass
class SpotnetPost:
    title: str
    poster: str
    category_id: int
    file_size: int
    description: str
    newsgroup: str
    nzb_segments: list[str] = field(default_factory=list)
    image_segments: list[str] = field(default_factory=list)
    spotnet_category: int | None = None  # Raw 0-3 from Spotnet XML
    spotnet_subcats: str = ""  # Raw subcat codes like "a0|b3|c1|d4"


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------

def parse_spotnet_body(lines: list[bytes]) -> SpotnetPost | None:
    """Parse raw NNTP article lines (including headers) into a SpotnetPost.

    Modern Spotnet posts store the XML across multiple X-XML: header lines,
    each continuation prefixed with 'X-XML: ' again (line-folded).
    We reassemble those before searching for XML markers.
    """
    decoded: list[str] = []
    for raw in lines:
        decoded.append(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)

    # Collect X-XML header fragments (each line starts with "X-XML: ")
    xml_parts: list[str] = []
    for line in decoded:
        stripped = line.rstrip("\r\n")
        if stripped.lower().startswith("x-xml:"):
            xml_parts.append(stripped[6:].lstrip(" "))

    if xml_parts:
        body = "".join(xml_parts)
    else:
        # Fallback: join all lines and search for XML marker
        body = "\n".join(decoded)
        for marker in ("<?xml", "<Spotnet", "<spotnet"):
            idx = body.find(marker)
            if idx != -1:
                body = body[idx:]
                break
        else:
            log.debug("No X-XML header or XML marker found in article")
            return None

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        log.debug("XML parse failed, trying <Posting> extraction: %s", exc)
        # Try extracting just the <Posting> block
        m = re.search(r"<Posting>.*?</Posting>", body, re.DOTALL | re.IGNORECASE)
        if not m:
            log.debug("No <Posting> block found")
            return None
        try:
            root = ET.fromstring(f"<Spotnet>{m.group(0)}</Spotnet>")
        except ET.ParseError as exc:
            log.debug("Fallback XML parse also failed: %s", exc)
            return None

    posting = root.find(".//Posting") or root.find("Posting")
    if posting is None:
        log.debug("No <Posting> element found in parsed XML")
        return None

    def txt(tag: str) -> str:
        el = posting.find(tag)
        return (el.text or "").strip() if el is not None else ""

    title = txt("Title")
    if not title:
        log.debug("Empty or missing Title element")
        return None

    poster    = txt("Poster")
    cat_raw   = txt("Category")      # "0"=Image/Video, "1"=Sound, "2"=Games, "3"=Applications
                                     # Actual XML uses zero-padded e.g. "01" — always parse as int
    newsgroup = txt("Newsgroup") or "alt.binaries.ftd"

    # Parse category early (needed for subcat normalisation below).
    # The XML uses 1-indexed, zero-padded values: "01"=Image/Video, "02"=Sound,
    # "03"=Games, "04"=Applications.  Subtract 1 to get 0-indexed (0=Image, 1=Sound…)
    # matching the CATEGORIES dict in categories.py.
    try:
        spotnet_category = int(cat_raw) - 1 if cat_raw else None
    except ValueError:
        spotnet_category = None

    # Collect and normalize Sub codes.
    # Wire format tag is <Sub> (not <SubCat> as the older PHP docs suggest).
    # Each value is {digits}{letter}{digits}, e.g. "01a09" or "01b03".
    # PHP parseFull() regex (\d+)([aAbBcCdDzZ])(\d+) normalises → letter+index: "a9", "b3".
    subcat_codes: list[str] = []
    for el in posting.iter("Sub"):          # real tag name is <Sub>
        if el.text and el.text.strip():
            m = _SUBCAT_RE.search(el.text.strip())
            if m:
                subcat_codes.append(m.group(2).lower() + str(int(m.group(3))))
    # Fallback: some older posts may use <SubCat>
    if not subcat_codes:
        for el in posting.iter("SubCat"):
            if el.text and el.text.strip():
                m = _SUBCAT_RE.search(el.text.strip())
                if m:
                    subcat_codes.append(m.group(2).lower() + str(int(m.group(3))))

    # Auto-generate z-category (type) when absent, matching PHP createSubcatZ behaviour
    if spotnet_category == 0 and not any(c.startswith("z") for c in subcat_codes):
        from src.scanner.categories import create_subcat_z
        z_auto = create_subcat_z(0, "|".join(subcat_codes))
        if z_auto:
            subcat_codes.append(z_auto.rstrip("|"))

    # Trailing pipe on every stored string so LIKE '%code|%' matches any position.
    subcat_string = "|".join(subcat_codes) + "|" if subcat_codes else ""
    is_tv = "z1" in subcat_codes  # z1 = Series type

    if spotnet_category == 0:
        category_id = _CAT_VIDEO_TV if is_tv else _CAT_VIDEO_MOVIE
    elif spotnet_category == 1:
        category_id = _CAT_AUDIO
    elif spotnet_category == 2:
        category_id = _CAT_IMAGE
    elif spotnet_category == 3:
        category_id = _CAT_PC
    else:
        category_id = _CAT_OTHER

    # Spotnet uses <Size> (bytes); some older posts use <FileSize>
    try:
        file_size = int(txt("Size") or txt("FileSize") or "0")
    except ValueError:
        file_size = 0

    desc_raw = txt("Description")
    if "<!--base64-->" in desc_raw:
        try:
            b64_part = desc_raw.split("<!--base64-->")[-1].strip()
            description = base64.b64decode(b64_part).decode("utf-8", errors="replace")
        except Exception:
            description = desc_raw
    else:
        description = desc_raw

    nzb_el = posting.find("NZB")
    segments: list[str] = []
    if nzb_el is not None:
        for seg in nzb_el.findall("Segment"):
            if seg.text and seg.text.strip():
                segments.append(seg.text.strip())

    image_el = posting.find("Image")
    image_segments: list[str] = []
    if image_el is not None:
        for seg in image_el.findall("Segment"):
            if seg.text and seg.text.strip():
                image_segments.append(seg.text.strip())

    return SpotnetPost(
        title=title,
        poster=poster,
        category_id=category_id,
        file_size=file_size,
        description=description,
        newsgroup=newsgroup,
        nzb_segments=segments,
        image_segments=image_segments,
        spotnet_category=spotnet_category,
        spotnet_subcats=subcat_string,
    )


# ---------------------------------------------------------------------------
# NZB assembly from Spotnet segments
# ---------------------------------------------------------------------------

def _unspecial_zip_str(data: bytes) -> bytes:
    """Reverse Spotnet's custom byte escaping (SpotWeb unspecialZipStr equivalent).

    =C → \\n, =B → \\r, =A → NUL, =D → =
    Order matters: process =C/=B/=A before =D so that =D= sequences decode correctly.
    """
    return (data
        .replace(b'=C', b'\n')
        .replace(b'=B', b'\r')
        .replace(b'=A', b'\x00')
        .replace(b'=D', b'='))


def _fetch_segments(nntp_conn, segment_ids: list[str]) -> bytes | None:
    """Fetch and concatenate raw body bytes from a list of Spotnet segment message-IDs."""
    chunks: list[bytes] = []
    for seg_id in segment_ids:
        mid = f"<{seg_id.strip('<>')}>"
        try:
            _, info = nntp_conn.article(mid)
        except Exception as exc:
            log.debug("Segment %s unavailable: %s", seg_id, exc)
            continue

        body_lines: list[bytes] = []
        in_body = False
        for line in info.lines:
            bl = line if isinstance(line, bytes) else line.encode("latin-1")
            if not in_body:
                if bl.rstrip(b"\r\n") == b"":
                    in_body = True
                continue
            body_lines.append(bl)

        chunks.append(b"".join(body_lines))

    return b"".join(chunks) if chunks else None


def _decode_spotnet_binary(raw_bytes: bytes) -> bytes:
    """Unescape and inflate Spotnet binary data (shared by NZB and image assembly)."""
    raw = _unspecial_zip_str(raw_bytes)
    try:
        return zlib.decompress(raw, -15)  # raw deflate = PHP gzinflate
    except zlib.error:
        return raw  # already uncompressed


def assemble_nzb(nntp_conn, segment_ids: list[str]) -> bytes | None:
    """Download Spotnet NZB segment articles and return the assembled NZB bytes."""
    if not segment_ids:
        return None
    raw = _fetch_segments(nntp_conn, segment_ids)
    return _decode_spotnet_binary(raw) if raw else None


def assemble_image(nntp_conn, segment_ids: list[str]) -> bytes | None:
    """Download Spotnet image segment articles and return the raw image bytes (JPEG/PNG)."""
    if not segment_ids:
        return None
    raw = _fetch_segments(nntp_conn, segment_ids)
    return _decode_spotnet_binary(raw) if raw else None
