"""Delivery Handbook business logic — migrated from main.py (Phase 5D).

Design: Functions that need `engine` or `SessionLocal` accept them as parameters.
Background task factories return closures that capture injected dependencies.
"""
from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import security_foundation as sec

from schemas.delivery_handbook import (
    HANDBOOK_ALLOWED_SUFFIXES,
    HANDBOOK_OCR_MAX_PAGES,
    HANDBOOK_OCR_ZOOM,
    HANDBOOK_SEARCH_BODY_MAX,
    HANDBOOK_STATUS_SET,
)

# ---------------------------------------------------------------------------
# Label / Status / Media helpers
# ---------------------------------------------------------------------------


def handbook_split_comma_labels(s: str) -> List[str]:
    return [x.strip() for x in str(s or "").replace("\uff0c", ",").split(",") if x.strip()]


def handbook_labels_to_json_array(s: str) -> str:
    return json.dumps(handbook_split_comma_labels(s), ensure_ascii=False)


def handbook_normalize_status(raw: str) -> str:
    v = str(raw or "").strip().lower()
    if v in HANDBOOK_STATUS_SET:
        return v
    return "draft"


def handbook_suffix_to_media_kind(ext: str) -> str:
    e = str(ext or "").lower()
    if e == ".pdf":
        return "pdf"
    if e in (".mp4", ".webm", ".ogg", ".mov"):
        return "video"
    if e in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
        return "audio"
    if e in (".doc", ".docx"):
        return "document"
    return "document"


def handbook_parse_json_list(raw: Optional[str], default: Optional[List[Any]] = None) -> List[Any]:
    default = default if default is not None else []
    if not raw or not str(raw).strip():
        return list(default)
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else list(default)
    except Exception:
        return list(default)


# ---------------------------------------------------------------------------
# PDF Outline extraction
# ---------------------------------------------------------------------------


def _toc_levels_to_tree(toc: List[List[Any]]) -> List[Dict[str, Any]]:
    if not toc:
        return []
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []
    for entry in toc:
        if not entry or len(entry) < 3:
            continue
        try:
            lvl = int(entry[0])
            title = str(entry[1] or "").strip() or "\u672a\u547d\u540d"
            page = int(entry[2])
        except (TypeError, ValueError):
            continue
        node = {"title": title, "page": max(1, page), "children": []}
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((lvl, node))
    return root


def pdf_outline_fitz(data: bytes) -> List[Dict[str, Any]]:
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        toc = doc.get_toc(simple=False) or doc.get_toc(simple=True)
        doc.close()
    except Exception:
        return []
    return _toc_levels_to_tree(toc) if toc else []


def _pypdf_outline_aux(items: Any, reader: Any) -> List[Dict[str, Any]]:
    if not items:
        return []
    if not isinstance(items, list):
        items = [items]
    tree: List[Dict[str, Any]] = []
    i = 0
    while i < len(items):
        el = items[i]
        if isinstance(el, list):
            if tree:
                tree[-1]["children"] = _pypdf_outline_aux(el, reader)
            else:
                tree.extend(_pypdf_outline_aux(el, reader))
            i += 1
            continue
        try:
            title = str(getattr(el, "title", "") or "").strip() or "\u672a\u547d\u540d"
            page = int(reader.get_destination_page_number(el)) + 1
        except Exception:
            i += 1
            continue
        node = {"title": title, "page": max(1, page), "children": []}
        tree.append(node)
        i += 1
        if i < len(items) and isinstance(items[i], list):
            node["children"] = _pypdf_outline_aux(items[i], reader)
            i += 1
    return tree


def pdf_outline_pypdf(data: bytes) -> List[Dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception:
        return []
    try:
        outline = reader.outline
    except Exception:
        return []
    if not outline:
        return []
    try:
        tree = _pypdf_outline_aux(outline, reader)
    except Exception:
        return []
    return tree if tree else []


_HANDBOOK_TOC_LINE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s*(?:\.{2,}|\u2026{1,}|\u00b7{2,}|\uff0a{2,}|\s{3,})\s*(\d{1,4})\s*$"
)

_HANDBOOK_TOC_INLINE = re.compile(
    r"(\d+(?:\.\d+)*)\s+(.+?)\s*(?:\.{2,}|\u2026{1,}|\u00b7{2,}|\s{2,})\s*(\d{1,4})"
)


def _handbook_normalize_toc_text(s: str) -> str:
    trans = str.maketrans(
        "\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\u3000\uff0e\uff0c",
        "0123456789 .,",
    )
    return (s or "").translate(trans)


def _section_key_depth(sec: str) -> int:
    parts = str(sec or "").strip().split(".")
    return max(0, len([p for p in parts if p]) - 1)


def _fitz_link_target_page_1based(doc: Any, link: Dict[str, Any]) -> Optional[int]:
    raw = link.get("page")
    if raw is not None:
        try:
            return int(raw) + 1
        except (TypeError, ValueError):
            pass
    uri = str(link.get("uri") or "").strip()
    if uri and not re.match(r"^https?://", uri, re.I):
        m = re.search(r"(?:[#&?]|^)(?:page|pg)\s*=\s*(\d+)", uri, re.I)
        if m:
            try:
                return max(1, int(m.group(1)))
            except ValueError:
                pass
    dest = link.get("dest")
    if dest is not None:
        try:
            p = getattr(dest, "page", None)
            if p is not None:
                pi = int(p)
                if pi >= 0:
                    return pi + 1
        except (TypeError, ValueError, AttributeError):
            pass
    rslv = getattr(doc, "resolve_link", None)
    if callable(rslv):
        try:
            loc = rslv(link)
            if loc is not None:
                if isinstance(loc, (list, tuple)) and len(loc) > 0:
                    try:
                        pi = int(loc[0])
                        if pi >= 0:
                            return pi + 1
                    except (TypeError, ValueError):
                        pass
                elif isinstance(loc, int) and loc >= 0:
                    return loc + 1
        except Exception:
            pass
    return None


def pdf_outline_from_internal_links(data: bytes) -> List[Dict[str, Any]]:
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return []
    LINK_GOTO = getattr(fitz, "LINK_GOTO", 1)
    LINK_GOTOR = getattr(fitz, "LINK_GOTOR", 5)
    candidates: List[Tuple[float, float, str, int]] = []
    max_scan = min(24, doc.page_count)
    for pno in range(max_scan):
        page = doc.load_page(pno)
        for link in page.get_links() or []:
            kind = link.get("kind")
            if kind not in (LINK_GOTO, LINK_GOTOR):
                continue
            dest_1 = _fitz_link_target_page_1based(doc, link)
            if dest_1 is None:
                continue
            rect = link.get("from")
            title = ""
            if rect:
                try:
                    r = fitz.Rect(rect)
                    title = page.get_textbox(r).strip()
                    if not title:
                        title = (page.get_text("text", clip=r) or "").strip()
                except Exception:
                    title = ""
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) > 160:
                title = title[:160].rstrip()
            if not title:
                if dest_1 != pno + 1:
                    title = f"\u00b7 \u7b2c{dest_1}\u9875"
                else:
                    continue
            if rect:
                r = fitz.Rect(rect)
                candidates.append((float(r.y0), float(r.x0), title, dest_1))
            else:
                candidates.append((0.0, 0.0, title, dest_1))
    doc.close()
    if len(candidates) < 1:
        return []
    candidates.sort(key=lambda t: (round(t[0], 2), round(t[1], 2)))
    found: List[Tuple[int, str, int]] = []
    seen: set = set()
    for _, _, title, pg in candidates:
        key = (title, pg)
        if key in seen:
            continue
        seen.add(key)
        raw_t = title.strip()
        m = re.match(r"^(\d+(?:\.\d+)*)", raw_t)
        sec = m.group(1) if m else ""
        depth = _section_key_depth(sec) if sec else 0
        found.append((depth, raw_t, max(1, pg)))
    if len(found) < 2:
        return []
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []
    for depth, title, page in found:
        node = {"title": title, "page": max(1, page), "children": []}
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((depth, node))
    return root


def pdf_outline_heuristic_text(data: bytes) -> List[Dict[str, Any]]:
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return []
    found: List[Tuple[int, str, int]] = []
    max_pages = min(16, doc.page_count)
    for pno in range(max_pages):
        page = doc.load_page(pno)
        try:
            text_val = page.get_text("text", sort=True) or page.get_text("text") or ""
        except Exception:
            text_val = page.get_text("text") or ""
        text_val = _handbook_normalize_toc_text(text_val)
        chunk = text_val
        if "\u76ee\u5f55" in chunk:
            idx = chunk.find("\u76ee\u5f55")
            chunk_after = chunk[idx: idx + 6000]
        else:
            chunk_after = chunk
        for m in _HANDBOOK_TOC_INLINE.finditer(chunk_after):
            sec, title, pstr = m.group(1), m.group(2).strip(), m.group(3)
            title = re.sub(r"\s+", " ", title).strip(" .,\uff0c")
            if not title or len(title) > 120:
                continue
            try:
                pg = int(pstr)
            except ValueError:
                continue
            depth = _section_key_depth(sec)
            found.append((depth, f"{sec} {title}", pg))
        for line in text_val.splitlines():
            raw = _handbook_normalize_toc_text(line.strip())
            if not raw:
                continue
            m = _HANDBOOK_TOC_LINE.match(raw)
            if not m and len(raw) < 140:
                m = re.match(r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s{2,}(\d{1,4})\s*$", raw)
            if not m and len(raw) < 140:
                m = re.match(r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s+(\d{1,4})\s*$", raw)
            if not m:
                continue
            sec, title, pstr = m.group(1), m.group(2).strip(), m.group(3)
            title = re.sub(r"\s+", " ", title).strip(" .,\uff0c")
            if not title or len(title) > 120:
                continue
            try:
                pg = int(pstr)
            except ValueError:
                continue
            depth = _section_key_depth(sec)
            found.append((depth, f"{sec} {title}", pg))
    doc.close()
    if not found:
        return []
    uniq: List[Tuple[int, str, int]] = []
    seen_line: set = set()
    for item in found:
        k = (item[1], item[2])
        if k in seen_line:
            continue
        seen_line.add(k)
        uniq.append(item)
    found = uniq
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []
    for depth, title, page in found:
        node = {"title": title, "page": max(1, page), "children": []}
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((depth, node))
    return root


def pdf_bytes_to_outline_tree(data: bytes) -> List[Dict[str, Any]]:
    tree = pdf_outline_fitz(data)
    if tree:
        return tree
    tree = pdf_outline_pypdf(data)
    if tree:
        return tree
    tree = pdf_outline_from_internal_links(data)
    if tree:
        return tree
    return pdf_outline_heuristic_text(data)


# ---------------------------------------------------------------------------
# Media cues / file path helpers
# ---------------------------------------------------------------------------


def handbook_normalize_media_cues(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip() or "\u951a\u70b9"
        try:
            sec = float(item.get("seconds", 0))
        except (TypeError, ValueError):
            sec = 0.0
        if sec < 0:
            sec = 0.0
        out.append({"label": label, "seconds": sec})
    return out


def handbook_client_dir_rel(client) -> str:
    return f"handbooks/client_{client.id}"


def safe_handbook_filename(name: str) -> str:
    base = os.path.basename(str(name or "")).strip()
    if not base:
        base = "handbook.bin"
    base = re.sub(r"[^\w\-. \u4e00-\u9fff]", "_", base)
    return (base[:200] if len(base) > 200 else base) or "handbook.bin"


# ---------------------------------------------------------------------------
# FTS helpers
# ---------------------------------------------------------------------------


def handbook_fts_delete_row(engine, row_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handbook_fts WHERE rowid = :rid"), {"rid": row_id})


def handbook_fts_upsert_row(engine, row_id: int, client_id: int, filename: str, body: str) -> None:
    fn = (filename or "")[:2000]
    bd = (body or "")[:HANDBOOK_SEARCH_BODY_MAX]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handbook_fts WHERE rowid = :rid"), {"rid": row_id})
        conn.execute(
            text(
                "INSERT INTO handbook_fts (rowid, original_filename, body, handbook_id, client_id) "
                "VALUES (:rid, :fn, :body, :hid, :cid)"
            ),
            {"rid": row_id, "fn": fn, "body": bd, "hid": row_id, "cid": client_id},
        )


def handbook_build_fts_query(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    s = re.sub(r'["\']', " ", s)
    tokens: List[str] = []
    for m in re.finditer(r"[\w.]+|[\u4e00-\u9fff]+", s):
        t = m.group(0)
        if t:
            tokens.append(t)
    if not tokens:
        return ""
    tokens = tokens[:24]
    return " OR ".join(f'"{t}"' for t in tokens)


def handbook_search_snippet(
    haystack: Optional[str],
    needle: str,
    max_len: int = 680,
    *,
    collapse_ws: bool = True,
) -> str:
    hay = haystack or ""
    nd = (needle or "").strip()

    def pack(s: str) -> str:
        s = (s or "").strip()
        if collapse_ws:
            return re.sub(r"\s+", " ", s).strip()
        return s

    if not hay:
        return ""
    if not nd:
        s0 = pack(hay[:max_len])
        return s0 + ("\u2026" if len(hay) > max_len else "")
    i = hay.find(nd)
    if i < 0:
        lh = hay.casefold()
        ln = nd.casefold()
        if ln and lh != hay:
            j = lh.find(ln)
            i = int(j) if j >= 0 else -1
    if i < 0:
        s0 = pack(hay[:max_len])
        return s0 + ("\u2026" if len(hay) > max_len else "")
    half = max_len // 2
    start = max(0, i - half)
    end = min(len(hay), start + max_len)
    start = max(0, end - max_len)
    frag = hay[start:end]
    frag = pack(frag)
    if start > 0:
        frag = "\u2026" + frag
    if end < len(hay):
        frag = frag + "\u2026"
    return frag


def handbook_query_terms(raw: str) -> List[str]:
    s = (raw or "").strip()
    if not s:
        return []
    terms = [s]
    for m in re.finditer(r"[\w.]+|[\u4e00-\u9fff]+", s):
        t = (m.group(0) or "").strip()
        if t and t not in terms:
            terms.append(t)
    return terms[:24]


def handbook_text_matches(text_value: Optional[str], terms: List[str]) -> bool:
    hay = (text_value or "").casefold()
    return bool(hay and any(t.casefold() in hay for t in terms if t))


# ---------------------------------------------------------------------------
# Search result locators
# ---------------------------------------------------------------------------


def handbook_locate_pdf_page(row, query: str, upload_dir: str) -> int:
    terms = handbook_query_terms(query)
    if not terms:
        return 1
    try:
        abs_path = sec.resolve_upload_path(upload_dir, (row.stored_path or "").strip())
    except ValueError:
        return 1
    if not os.path.isfile(abs_path):
        return 1
    try:
        import fitz
    except ImportError:
        return 1
    doc = None
    try:
        doc = fitz.open(abs_path)
        for i in range(len(doc)):
            try:
                page_text = doc.load_page(i).get_text() or ""
            except Exception:
                page_text = ""
            if handbook_text_matches(page_text, terms):
                return i + 1
    except Exception:
        return 1
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
    return 1


def handbook_locate_media_seconds(row, query: str) -> Optional[float]:
    terms = handbook_query_terms(query)
    cues = handbook_cues_from_json_string(getattr(row, "media_cues_json", None))
    if not cues:
        return None
    for c in cues:
        if handbook_text_matches(str(c.get("label") or ""), terms):
            return float(c.get("seconds") or 0)
    return None


# ---------------------------------------------------------------------------
# PDF text extraction / rendering / OCR
# ---------------------------------------------------------------------------


def pdf_plain_text_and_pagecount(data: bytes) -> Tuple[str, int]:
    try:
        import fitz
    except ImportError:
        return "", 0
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return "", 0
    try:
        n = len(doc)
        parts: List[str] = []
        for i in range(n):
            try:
                parts.append(doc.load_page(i).get_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts), n
    finally:
        try:
            doc.close()
        except Exception:
            pass


def pdf_plain_text_pages(data: bytes) -> List[Dict[str, Any]]:
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return []
    try:
        pages: List[Dict[str, Any]] = []
        for i in range(len(doc)):
            try:
                text_value = doc.load_page(i).get_text() or ""
            except Exception:
                text_value = ""
            pages.append({"page": i + 1, "text": text_value})
        return pages
    finally:
        try:
            doc.close()
        except Exception:
            pass


def pdf_render_page_png(data: bytes, page_no: int, query: str = "") -> bytes:
    try:
        import fitz
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"PDF \u6e32\u67d3\u4f9d\u8d56\u672a\u5b89\u88c5\uff08{e}\uff09")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF \u6253\u5f00\u5931\u8d25\uff08{e}\uff09")
    try:
        if len(doc) <= 0:
            raise HTTPException(status_code=400, detail="PDF \u65e0\u9875\u9762")
        idx = max(0, min(int(page_no or 1) - 1, len(doc) - 1))
        page = doc.load_page(idx)
        for term in handbook_query_terms(query):
            try:
                rects = page.search_for(term)
            except Exception:
                rects = []
            for rect in rects:
                try:
                    page.draw_rect(
                        rect,
                        color=(0.95, 0.58, 0.0),
                        fill=(1.0, 0.86, 0.1),
                        fill_opacity=0.38,
                        width=0.8,
                        overlay=True,
                    )
                except Exception:
                    pass
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        return pix.tobytes("png")
    finally:
        try:
            doc.close()
        except Exception:
            pass


def pdf_text_suggests_ocr(plain: str, page_count: int) -> bool:
    t = (plain or "").strip()
    if page_count <= 0:
        return False
    if len(t) < 80:
        return True
    avg = len(t) / max(page_count, 1)
    return avg < 35


def pdf_ocr_tesseract(data: bytes) -> Tuple[str, str]:
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io as _io
    except ImportError as e:
        return "", f"Python \u4f9d\u8d56\u672a\u5b89\u88c5\uff08{e}\uff09"
    if os.environ.get("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    doc = None
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        return "", str(e)
    mat = fitz.Matrix(HANDBOOK_OCR_ZOOM, HANDBOOK_OCR_ZOOM)
    parts: List[str] = []
    try:
        n = min(len(doc), HANDBOOK_OCR_MAX_PAGES)
        ocr_fatal = ""
        for i in range(n):
            try:
                pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes("png")
                img = Image.open(_io.BytesIO(img_bytes)).convert("RGB")
                txt = pytesseract.image_to_string(img, lang="chi_sim+eng") or ""
                parts.append(txt)
            except pytesseract.TesseractNotFoundError:
                ocr_fatal = (
                    "\u672a\u68c0\u6d4b\u5230 Tesseract \u53ef\u6267\u884c\u7a0b\u5e8f\uff0c"
                    "\u8bf7\u5b89\u88c5\u5e76\u628a tesseract \u52a0\u5165 PATH\uff0c"
                    "\u6216\u8bbe\u7f6e\u73af\u5883\u53d8\u91cf TESSERACT_CMD"
                )
                break
            except Exception:
                parts.append("")
        if ocr_fatal:
            return "", ocr_fatal
        return "\n".join(parts), ""
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Manual search blob (non-PDF metadata indexing)
# ---------------------------------------------------------------------------


def handbook_manual_search_blob(r) -> str:
    lines: List[str] = []
    fn = (r.original_filename or "").strip()
    if fn:
        lines.append(fn)
        base = os.path.splitext(fn)[0].strip()
        if base and base != fn:
            lines.append(base)
    vl = str(getattr(r, "version_label", None) or "").strip()
    if vl:
        lines.append(vl)
    for lst, prefix in (
        (handbook_parse_json_list(getattr(r, "tags_json", None)), "\u6807\u7b7e"),
        (handbook_parse_json_list(getattr(r, "permission_departments_json", None)), "\u90e8\u95e8"),
        (handbook_parse_json_list(getattr(r, "permission_levels_json", None)), "\u7ea7\u522b"),
    ):
        for x in lst:
            sx = str(x).strip()
            if sx:
                lines.append(f"{prefix} {sx}")
                lines.append(sx)
    mk = (getattr(r, "media_kind", None) or "").strip()
    if mk == "video":
        lines.append("\u89c6\u9891")
    elif mk == "audio":
        lines.append("\u97f3\u9891")
    elif mk == "document":
        lines.append("\u6587\u6863")
    try:
        cues = json.loads(getattr(r, "media_cues_json", None) or "[]")
    except Exception:
        cues = []
    if isinstance(cues, list):
        for c in cues:
            if not isinstance(c, dict):
                continue
            label = str(c.get("label") or "").strip()
            if not label:
                continue
            lines.append(label)
            sec = c.get("seconds")
            if sec is not None:
                try:
                    lines.append(f"{label} {float(sec)}\u79d2")
                except (TypeError, ValueError):
                    lines.append(f"{label} {sec}\u79d2")
    return "\n".join(x for x in lines if str(x).strip())


# ---------------------------------------------------------------------------
# Background task factories (closure pattern)
# ---------------------------------------------------------------------------


def make_background_index_manual_meta(
    session_factory: Callable,
    engine,
    HandbookFile: Type,
) -> Callable[[int], None]:
    """Factory: returns a background task fn(row_id) for non-PDF metadata indexing."""

    def _background_index_manual_meta(row_id: int) -> None:
        db = session_factory()
        try:
            row = db.query(HandbookFile).filter(HandbookFile.id == row_id).first()
            if not row:
                return
            mk = (row.media_kind or "").strip() or handbook_suffix_to_media_kind(
                os.path.splitext(row.original_filename or "")[1].lower()
            )
            if mk == "pdf":
                return
            if mk not in ("video", "audio", "document"):
                row.search_status = "skipped"
                row.search_method = "none"
                row.search_body = ""
                row.search_error = ""
                row.updated_at = datetime.now()
                db.commit()
                try:
                    handbook_fts_delete_row(engine, row_id)
                except Exception:
                    pass
                return
            blob = handbook_manual_search_blob(row).strip()
            row.search_body = blob[:HANDBOOK_SEARCH_BODY_MAX]
            row.search_method = "meta"
            row.search_status = "indexed" if blob else "skipped"
            row.search_error = ""
            row.updated_at = datetime.now()
            db.commit()
            if blob:
                handbook_fts_upsert_row(engine, int(row.id), int(row.client_id), row.original_filename or "", row.search_body)
            else:
                try:
                    handbook_fts_delete_row(engine, row_id)
                except Exception:
                    pass
        except Exception as e:
            try:
                r2 = db.query(HandbookFile).filter(HandbookFile.id == row_id).first()
                if r2 and (r2.media_kind or "").strip() in ("video", "audio", "document"):
                    r2.search_status = "failed"
                    r2.search_error = str(e)[:500]
                    r2.updated_at = datetime.now()
                    db.commit()
            except Exception:
                db.rollback()
            try:
                handbook_fts_delete_row(engine, row_id)
            except Exception:
                pass
        finally:
            db.close()

    return _background_index_manual_meta


def make_background_index_pdf(
    session_factory: Callable,
    engine,
    HandbookFile: Type,
    upload_dir: str,
) -> Callable[[int], None]:
    """Factory: returns a background task fn(row_id) for PDF text extraction + FTS indexing."""

    def _background_index_pdf(row_id: int) -> None:
        db = session_factory()
        try:
            row = db.query(HandbookFile).filter(HandbookFile.id == row_id).first()
            if not row:
                return
            mk = (row.media_kind or "").strip() or handbook_suffix_to_media_kind(
                os.path.splitext(row.original_filename or "")[1].lower()
            )
            if mk != "pdf":
                row.search_status = "skipped"
                row.search_method = "none"
                row.search_error = ""
                row.search_body = ""
                row.updated_at = datetime.now()
                db.commit()
                handbook_fts_delete_row(engine, row_id)
                return
            try:
                abs_path = sec.resolve_upload_path(upload_dir, (row.stored_path or "").strip())
            except ValueError:
                abs_path = None
            if not abs_path or not os.path.isfile(abs_path):
                row.search_status = "failed"
                row.search_method = ""
                row.search_error = "\u6587\u4ef6\u4e0d\u5b58\u5728"
                row.search_body = ""
                row.updated_at = datetime.now()
                db.commit()
                handbook_fts_delete_row(engine, row_id)
                return
            row.search_status = "indexing"
            row.search_error = ""
            db.commit()

            try:
                with open(abs_path, "rb") as fp:
                    data = fp.read()
            except OSError as e:
                row.search_status = "failed"
                row.search_error = str(e)
                row.search_body = ""
                row.updated_at = datetime.now()
                db.commit()
                handbook_fts_delete_row(engine, row_id)
                return

            extracted, pg = pdf_plain_text_and_pagecount(data)
            method = "text_extract"
            final_text = extracted
            if pdf_text_suggests_ocr(extracted, max(pg, 1)):
                ocr_txt, err = pdf_ocr_tesseract(data)
                if err:
                    row.search_body = extracted[:HANDBOOK_SEARCH_BODY_MAX]
                    row.updated_at = datetime.now()
                    ext_ok = bool((extracted or "").strip())
                    if ext_ok:
                        row.search_status = "indexed"
                        row.search_method = "text_extract"
                        row.search_error = f"OCR \u672a\u6267\u884c\uff08{err[:400]}\uff09"
                        db.commit()
                        handbook_fts_upsert_row(engine, row.id, row.client_id, row.original_filename or "", row.search_body)
                        return
                    row.search_status = "failed"
                    row.search_method = ""
                    row.search_error = err
                    db.commit()
                    handbook_fts_delete_row(engine, row_id)
                    return
                merged = ((ocr_txt or "").strip())
                final_text = merged if merged else extracted
                method = "ocr" if merged else method
            trimmed = final_text.strip()
            row.search_body = final_text[:HANDBOOK_SEARCH_BODY_MAX]
            row.search_method = method
            row.search_status = "indexed" if trimmed else "failed"
            row.search_error = "" if trimmed else "\u672a\u8bc6\u522b\u5230\u53ef\u8bfb\u6587\u672c\uff08\u53ef\u68c0\u67e5\u662f\u5426\u4e3a\u52a0\u5bc6 PDF\uff09"
            row.updated_at = datetime.now()
            db.commit()
            if trimmed:
                handbook_fts_upsert_row(engine, row.id, row.client_id, row.original_filename or "", row.search_body)
            else:
                handbook_fts_delete_row(engine, row_id)
        except Exception as e:
            try:
                r2 = db.query(HandbookFile).filter(HandbookFile.id == row_id).first()
                if r2:
                    r2.search_status = "failed"
                    r2.search_error = str(e)[:500]
                    r2.updated_at = datetime.now()
                    db.commit()
            except Exception:
                db.rollback()
            try:
                handbook_fts_delete_row(engine, row_id)
            except Exception:
                pass
        finally:
            db.close()

    return _background_index_pdf


# ---------------------------------------------------------------------------
# Row serialization
# ---------------------------------------------------------------------------


def handbook_outline_coerce(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        v = json.loads(raw or "[]")
    except Exception:
        return []
    return v if isinstance(v, list) else []


def handbook_cues_from_json_string(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        v = json.loads(raw or "[]")
    except Exception:
        return []
    return handbook_normalize_media_cues(v if isinstance(v, list) else [])


def handbook_dt_iso(val: Any) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    try:
        return str(val)
    except Exception:
        return ""


def handbook_row_to_dict(r, file_access_url_fn: Callable[[str], str]) -> Dict[str, Any]:
    sp = (r.stored_path or "").strip()
    mk = (getattr(r, "media_kind", None) or "").strip()
    if not mk:
        mk = handbook_suffix_to_media_kind(os.path.splitext(r.original_filename or "")[1].lower())
    outline = handbook_outline_coerce(getattr(r, "pdf_outline_json", None))
    return {
        "id": r.id,
        "client_id": r.client_id,
        "original_filename": r.original_filename or "",
        "stored_path": sp,
        "preview_url": file_access_url_fn(sp),
        "version_label": (getattr(r, "version_label", None) or "") or "",
        "status": handbook_normalize_status(getattr(r, "status", None) or "draft"),
        "tags": handbook_parse_json_list(getattr(r, "tags_json", None)),
        "permission_departments": handbook_parse_json_list(getattr(r, "permission_departments_json", None)),
        "permission_levels": handbook_parse_json_list(getattr(r, "permission_levels_json", None)),
        "media_kind": mk,
        "pdf_outline": outline,
        "media_cues": handbook_cues_from_json_string(getattr(r, "media_cues_json", None)),
        "search_status": ("pending" if getattr(r, "search_status", None) is None else str(r.search_status).strip())
        or "pending",
        "search_method": (getattr(r, "search_method", None) or "").strip(),
        "search_error": (getattr(r, "search_error", None) or "").strip(),
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": handbook_dt_iso(getattr(r, "updated_at", None)),
    }
