#!/usr/bin/env python3
"""
███╗   ██╗ ██████╗  ██╗██████╗       ██████╗  ██████╗  ██████╗ ██╗  ██╗
████╗  ██║██╔═████╗███║██╔══██╗      ██╔══██╗██╔═══██╗██╔═══██╗██║ ██╔╝
██╔██╗ ██║██║██╔██║╚██║██║  ██║█████╗██████╔╝██║   ██║██║   ██║█████╔╝
██║╚██╗██║████╔╝██║ ██║██║  ██║╚════╝██╔══██╗██║   ██║██║   ██║██╔═██╗
██║ ╚████║╚██████╔╝ ██║██████╔╝      ██████╔╝╚██████╔╝╚██████╔╝██║  ██╗
╚═╝  ╚═══╝ ╚═════╝  ╚═╝╚═════╝       ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝

N01D Book Reader - Self-Hosted eBook Library & OPDS Server
Part of the NullSec Toolkit
Serves OPDS catalog for mobile readers (iPad, Android, etc.)
"""

import os
import sys
import json
import hashlib
import mimetypes
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, quote, urlparse, parse_qs
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.etree.ElementTree as ET

# Optional PDF metadata extraction
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# ─── Configuration ──────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")
DOOMSDAY_URL = "http://192.168.40.22:8074"

DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8074,
    "library_name": "N01D Book Reader",
    "library_dirs": [
        os.path.expanduser("~/nullsec-repos"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Books"),
    ],
    "supported_formats": [".pdf", ".epub", ".mobi", ".azw3", ".cbz", ".cbr", ".fb2", ".djvu", ".txt"],
    "scan_interval_minutes": 30,
    "cover_cache_dir": os.path.join(os.path.dirname(os.path.abspath(__file__)), "covers"),
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return dict(DEFAULT_CONFIG)


# ─── Database ───────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT DEFAULT 'Unknown',
            path TEXT NOT NULL UNIQUE,
            format TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            category TEXT DEFAULT 'Uncategorized',
            description TEXT DEFAULT '',
            date_added TEXT NOT NULL,
            date_modified TEXT NOT NULL,
            cover_path TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            pages INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY,
            description TEXT DEFAULT '',
            book_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_category ON books(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_format ON books(format)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_author ON books(author)")
    conn.commit()
    return conn


def categorize_book(filepath: str) -> str:
    """Categorize a book based on its file path."""
    path_lower = filepath.lower()
    categories = {
        "Penetration Testing": ["pentest", "pentesting", "offensive", "exploit", "payload", "hack-tools", "hacking-tools"],
        "Red Team": ["red-team", "redteam", "red_team", "attack", "c2", "backdoor", "rootkit", "malware"],
        "Blue Team": ["blue-team", "defense", "forensic", "incident", "hardening", "security-hardening"],
        "OSINT": ["osint", "recon", "reconnaissance", "enumeration", "subdomain"],
        "Networking": ["network", "nmap", "wifi", "wireless", "bluetooth", "tcp", "dns", "packet"],
        "Web Security": ["web", "xss", "sqli", "injection", "owasp", "burp", "websocket"],
        "Cryptography": ["crypt", "cipher", "hash", "encrypt", "ssl", "tls"],
        "Reverse Engineering": ["reverse", "disassembl", "binary", "firmware", "malware-analysis"],
        "Mobile Security": ["android", "ios", "mobile", "iphone", "apk"],
        "Cloud Security": ["cloud", "aws", "azure", "gcp", "docker", "kubernetes", "k8s"],
        "CTF": ["ctf", "capture-the-flag", "challenge"],
        "Programming": ["python", "rust", "julia", "programming", "scripting", "code"],
        "IoT & Hardware": ["iot", "scada", "ics", "plc", "rfid", "flipper", "uart", "jtag", "sdr", "automotive"],
        "Privacy & Anonymity": ["privacy", "tor", "vpn", "anonymous", "steganograph"],
        "Cheatsheets": ["cheat", "reference", "guide", "checklist"],
        "AI & Machine Learning": ["ai", "llm", "machine-learning", "ml-", "adversarial"],
        "Bug Bounty": ["bugbounty", "bug-bounty", "bounty"],
        "Documentation": ["docs", "manual", "guide", "readme"],
    }
    for cat, keywords in categories.items():
        if any(kw in path_lower for kw in keywords):
            return cat
    return "Uncategorized"


def extract_metadata(filepath: str) -> dict:
    """Extract metadata from a file."""
    path = Path(filepath)
    meta = {
        "title": path.stem.replace("-", " ").replace("_", " ").title(),
        "author": "Unknown",
        "description": "",
        "pages": 0,
    }

    if HAS_PYMUPDF and path.suffix.lower() in (".pdf", ".epub"):
        try:
            doc = fitz.open(filepath)
            md = doc.metadata
            if md:
                if md.get("title"):
                    meta["title"] = md["title"]
                if md.get("author"):
                    meta["author"] = md["author"]
                if md.get("subject"):
                    meta["description"] = md["subject"]
            meta["pages"] = doc.page_count
            doc.close()
        except Exception:
            pass

    return meta


def scan_library(config, db_conn):
    """Scan library directories for books."""
    print(f"[*] Scanning library directories...")
    found = 0
    formats = set(config["supported_formats"])

    for lib_dir in config["library_dirs"]:
        lib_path = Path(lib_dir)
        if not lib_path.exists():
            print(f"  [!] Directory not found: {lib_dir}")
            continue

        print(f"  [>] Scanning: {lib_dir}")
        for root, dirs, files in os.walk(lib_path):
            # Skip hidden dirs, venvs, node_modules
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "node_modules", "__pycache__", ".git")]
            for fname in files:
                fpath = os.path.join(root, fname)
                ext = Path(fname).suffix.lower()
                if ext not in formats:
                    continue
                # Skip tiny files
                try:
                    fsize = os.path.getsize(fpath)
                except OSError:
                    continue
                # Text files must be > 50KB to qualify as "books"
                min_size = 51200 if ext == ".txt" else 5120
                if fsize < min_size:
                    continue

                file_id = hashlib.md5(fpath.encode()).hexdigest()
                now = datetime.now(timezone.utc).isoformat()

                # Check if already in DB
                existing = db_conn.execute("SELECT id FROM books WHERE id = ?", (file_id,)).fetchone()
                if existing:
                    continue

                meta = extract_metadata(fpath)
                category = categorize_book(fpath)

                try:
                    db_conn.execute("""
                        INSERT OR IGNORE INTO books (id, title, author, path, format, size, category, description, date_added, date_modified, language, pages)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        file_id, meta["title"], meta["author"], fpath, ext,
                        fsize, category, meta["description"], now, now,
                        "en", meta["pages"]
                    ))
                    found += 1
                except sqlite3.IntegrityError:
                    pass

    db_conn.commit()

    # Update category counts
    db_conn.execute("DELETE FROM categories")
    cats = db_conn.execute("SELECT category, COUNT(*) FROM books GROUP BY category ORDER BY category").fetchall()
    for cat, count in cats:
        db_conn.execute("INSERT INTO categories (name, book_count) VALUES (?, ?)", (cat, count))
    db_conn.commit()

    total = db_conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    print(f"  [✓] Found {found} new books ({total} total in library)")
    return total


# ─── OPDS Feed Generator ───────────────────────────────────────

ATOM_NS = "http://www.w3.org/2005/Atom"
OPDS_NS = "http://opds-spec.org/2010/catalog"
DC_NS = "http://purl.org/dc/terms/"
THR_NS = "http://purl.org/syndication/thread/1.0"

ET.register_namespace("", ATOM_NS)
ET.register_namespace("opds", OPDS_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("thr", THR_NS)


def make_opds_feed(feed_id, title, entries, updated=None, links=None):
    """Build an OPDS Atom feed."""
    if updated is None:
        updated = datetime.now(timezone.utc).isoformat()

    feed = Element(f"{{{ATOM_NS}}}feed")
    SubElement(feed, f"{{{ATOM_NS}}}id").text = feed_id
    SubElement(feed, f"{{{ATOM_NS}}}title").text = title
    SubElement(feed, f"{{{ATOM_NS}}}updated").text = updated

    author = SubElement(feed, f"{{{ATOM_NS}}}author")
    SubElement(author, f"{{{ATOM_NS}}}name").text = "N01D Book Reader"

    if links:
        for rel, href, link_type in links:
            link_el = SubElement(feed, f"{{{ATOM_NS}}}link")
            link_el.set("rel", rel)
            link_el.set("href", href)
            if link_type:
                link_el.set("type", link_type)

    for entry_data in entries:
        entry = SubElement(feed, f"{{{ATOM_NS}}}entry")
        SubElement(entry, f"{{{ATOM_NS}}}id").text = entry_data["id"]
        SubElement(entry, f"{{{ATOM_NS}}}title").text = entry_data["title"]
        SubElement(entry, f"{{{ATOM_NS}}}updated").text = entry_data.get("updated", updated)

        if "content" in entry_data:
            content = SubElement(entry, f"{{{ATOM_NS}}}content")
            content.set("type", "text")
            content.text = entry_data["content"]

        if "author" in entry_data and entry_data["author"] != "Unknown":
            a = SubElement(entry, f"{{{ATOM_NS}}}author")
            SubElement(a, f"{{{ATOM_NS}}}name").text = entry_data["author"]

        if "category" in entry_data:
            cat = SubElement(entry, f"{{{ATOM_NS}}}category")
            cat.set("term", entry_data["category"])
            cat.set("label", entry_data["category"])

        for link in entry_data.get("links", []):
            link_el = SubElement(entry, f"{{{ATOM_NS}}}link")
            link_el.set("rel", link["rel"])
            link_el.set("href", link["href"])
            if "type" in link:
                link_el.set("type", link["type"])
            if "title" in link:
                link_el.set("title", link["title"])
            if "count" in link:
                link_el.set(f"{{{THR_NS}}}count", str(link["count"]))

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(feed, encoding="unicode")


# ─── MIME Types ─────────────────────────────────────────────────

BOOK_MIMES = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".mobi": "application/x-mobipocket-ebook",
    ".azw3": "application/x-mobi8-ebook",
    ".cbz": "application/x-cbz",
    ".cbr": "application/x-cbr",
    ".fb2": "application/fb2+xml",
    ".djvu": "image/vnd.djvu",
    ".txt": "text/plain",
}


# ─── HTTP Handler ───────────────────────────────────────────────

class N01DBookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for N01D Book Reader."""

    server_version = "N01D-BookReader/1.0"

    def log_message(self, format, *args):
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

    def send_opds(self, xml_content):
        self.send_response(200)
        self.send_header("Content-Type", "application/atom+xml;profile=opds-catalog;charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(xml_content.encode("utf-8"))

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def proxy_doomsday(self, doomsday_book_id, endpoint="chapters/0/text", content_type=None):
        """Proxy a request to the Doomsday N01D server."""
        try:
            import urllib.request
            url = f"{DOOMSDAY_URL}/api/books/{doomsday_book_id}/{endpoint}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                ct = content_type or resp.headers.get('Content-Type', 'application/octet-stream')
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_error(502, f"Doomsday proxy error: {e}")

    def send_file(self, filepath, content_type=None):
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        if content_type is None:
            ext = Path(filepath).suffix.lower()
            content_type = BOOK_MIMES.get(ext, mimetypes.guess_type(filepath)[0] or "application/octet-stream")
        fsize = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(fsize))
        self.send_header("Content-Disposition", f'attachment; filename="{Path(filepath).name}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"
        params = parse_qs(parsed.query)
        db = sqlite3.connect(DB_FILE)
        db.row_factory = sqlite3.Row

        try:
            # ── OPDS Endpoints ──
            if path == "/opds" or path == "/opds/":
                self._opds_root(db)
            elif path == "/opds/categories":
                self._opds_categories(db)
            elif path.startswith("/opds/category/"):
                cat = unquote(path.split("/opds/category/", 1)[1])
                self._opds_category_books(db, cat)
            elif path == "/opds/all":
                self._opds_all_books(db)
            elif path == "/opds/recent":
                self._opds_recent(db)
            elif path == "/opds/search":
                query = params.get("q", [""])[0]
                self._opds_search(db, query)
            elif path.startswith("/opds/book/"):
                book_id = path.split("/opds/book/", 1)[1]
                self._opds_book_entry(db, book_id)

            # ── Reader ──
            elif path.startswith("/read/"):
                book_id = path.split("/read/", 1)[1]
                row = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
                if row:
                    self._reader_ui(db, dict(row))
                else:
                    self.send_error(404, "Book not found")

            # ── Book content API ──
            elif path.startswith("/api/book/") and path.endswith("/content"):
                book_id = path.split("/api/book/", 1)[1].rsplit("/content", 1)[0]
                self._api_book_content(db, book_id)

            # ── Download ──
            elif path.startswith("/download/"):
                book_id = path.split("/download/", 1)[1]
                row = db.execute("SELECT path, id FROM books WHERE id = ?", (book_id,)).fetchone()
                if row:
                    filepath = row["path"]
                    if filepath.startswith("doomsday://"):
                        # Proxy from Doomsday server
                        doom_id = filepath.split("://")[1].split("/")[0]
                        self.proxy_doomsday(doom_id, "chapters/0/text")
                    else:
                        self.send_file(filepath)
                else:
                    self.send_error(404, "Book not found")

            # ── Cover proxy for Doomsday books ──
            elif path.startswith("/cover/"):
                book_id = path.split("/cover/", 1)[1]
                row = db.execute("SELECT path FROM books WHERE id = ?", (book_id,)).fetchone()
                if row and row["path"].startswith("doomsday://"):
                    doom_id = row["path"].split("://")[1].split("/")[0]
                    self.proxy_doomsday(doom_id, "cover", "image/jpeg")
                else:
                    self.send_error(404)

            # ── Sync from Doomsday ──
            elif path == "/api/sync":
                import subprocess
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_doomsday.py")
                result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=300)
                self.send_json({"status": "ok", "output": result.stdout})

            # ── API Endpoints ──
            elif path == "/api/stats":
                self._api_stats(db)
            elif path == "/api/books":
                self._api_books(db, params)
            elif path == "/api/categories":
                cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
                self.send_json([dict(c) for c in cats])
            elif path == "/api/scan":
                config = load_config()
                count = scan_library(config, db)
                self.send_json({"status": "ok", "total": count})

            # ── Web UI ──
            elif path == "/" or path == "":
                self._web_ui(db)

            # ── Static assets ──
            elif path.startswith("/static/"):
                asset = os.path.join(os.path.dirname(os.path.abspath(__file__)), path.lstrip("/"))
                if os.path.exists(asset):
                    self.send_file(asset, mimetypes.guess_type(asset)[0])
                else:
                    self.send_error(404)
            else:
                self.send_error(404, "Not found")
        finally:
            db.close()

    # ── OPDS Handlers ───────────────────────────────────────────

    def _opds_root(self, db):
        total = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        entries = [
            {
                "id": "urn:n01d:all",
                "title": f"All Books ({total})",
                "content": "Browse the complete library",
                "links": [{"rel": "subsection", "href": "/opds/all",
                           "type": "application/atom+xml;profile=opds-catalog;kind=acquisition"}],
            },
            {
                "id": "urn:n01d:recent",
                "title": "Recently Added",
                "content": "Latest additions to the library",
                "links": [{"rel": "subsection", "href": "/opds/recent",
                           "type": "application/atom+xml;profile=opds-catalog;kind=acquisition"}],
            },
            {
                "id": "urn:n01d:categories",
                "title": "Categories",
                "content": "Browse by category",
                "links": [{"rel": "subsection", "href": "/opds/categories",
                           "type": "application/atom+xml;profile=opds-catalog;kind=navigation"}],
            },
        ]
        links = [
            ("self", "/opds", "application/atom+xml;profile=opds-catalog;kind=navigation"),
            ("start", "/opds", "application/atom+xml;profile=opds-catalog;kind=navigation"),
            ("search", "/opds/search?q={searchTerms}", "application/atom+xml"),
        ]
        xml = make_opds_feed("urn:n01d:root", "N01D Book Reader", entries, links=links)
        self.send_opds(xml)

    def _opds_categories(self, db):
        cats = db.execute("SELECT name, book_count FROM categories ORDER BY name").fetchall()
        entries = []
        for cat in cats:
            entries.append({
                "id": f"urn:n01d:category:{cat['name']}",
                "title": f"{cat['name']} ({cat['book_count']})",
                "content": f"{cat['book_count']} books",
                "links": [{"rel": "subsection", "href": f"/opds/category/{quote(cat['name'])}",
                           "type": "application/atom+xml;profile=opds-catalog;kind=acquisition",
                           "count": cat['book_count']}],
            })
        links = [
            ("self", "/opds/categories", "application/atom+xml;profile=opds-catalog;kind=navigation"),
            ("up", "/opds", "application/atom+xml;profile=opds-catalog;kind=navigation"),
        ]
        xml = make_opds_feed("urn:n01d:categories", "Categories", entries, links=links)
        self.send_opds(xml)

    def _opds_category_books(self, db, category):
        books = db.execute("SELECT * FROM books WHERE category = ? ORDER BY title", (category,)).fetchall()
        entries = [self._book_to_opds_entry(b) for b in books]
        links = [
            ("self", f"/opds/category/{quote(category)}", "application/atom+xml;profile=opds-catalog;kind=acquisition"),
            ("up", "/opds/categories", "application/atom+xml;profile=opds-catalog;kind=navigation"),
        ]
        xml = make_opds_feed(f"urn:n01d:category:{category}", f"Category: {category}", entries, links=links)
        self.send_opds(xml)

    def _opds_all_books(self, db):
        books = db.execute("SELECT * FROM books ORDER BY title").fetchall()
        entries = [self._book_to_opds_entry(b) for b in books]
        links = [
            ("self", "/opds/all", "application/atom+xml;profile=opds-catalog;kind=acquisition"),
            ("up", "/opds", "application/atom+xml;profile=opds-catalog;kind=navigation"),
        ]
        xml = make_opds_feed("urn:n01d:all", "All Books", entries, links=links)
        self.send_opds(xml)

    def _opds_recent(self, db):
        books = db.execute("SELECT * FROM books ORDER BY date_added DESC LIMIT 50").fetchall()
        entries = [self._book_to_opds_entry(b) for b in books]
        links = [
            ("self", "/opds/recent", "application/atom+xml;profile=opds-catalog;kind=acquisition"),
            ("up", "/opds", "application/atom+xml;profile=opds-catalog;kind=navigation"),
        ]
        xml = make_opds_feed("urn:n01d:recent", "Recently Added", entries, links=links)
        self.send_opds(xml)

    def _opds_search(self, db, query):
        if not query:
            entries = []
        else:
            q = f"%{query}%"
            books = db.execute(
                "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR category LIKE ? ORDER BY title",
                (q, q, q)
            ).fetchall()
            entries = [self._book_to_opds_entry(b) for b in books]
        xml = make_opds_feed("urn:n01d:search", f"Search: {query}", entries)
        self.send_opds(xml)

    def _opds_book_entry(self, db, book_id):
        book = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            self.send_error(404)
            return
        entries = [self._book_to_opds_entry(book)]
        xml = make_opds_feed(f"urn:n01d:book:{book_id}", book["title"], entries)
        self.send_opds(xml)

    def _book_to_opds_entry(self, book):
        ext = book["format"]
        mime = BOOK_MIMES.get(ext, "application/octet-stream")
        return {
            "id": f"urn:n01d:book:{book['id']}",
            "title": book["title"],
            "author": book["author"],
            "updated": book["date_modified"],
            "category": book["category"],
            "content": book["description"] or f"{book['category']} • {ext.upper().strip('.')} • {book['size'] // 1024}KB",
            "links": [
                {
                    "rel": "http://opds-spec.org/acquisition",
                    "href": f"/download/{book['id']}",
                    "type": mime,
                    "title": f"Download {ext.upper().strip('.')}",
                },
            ],
        }

    # ── API Handlers ────────────────────────────────────────────

    def _api_stats(self, db):
        total = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        cats = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        formats = db.execute("SELECT format, COUNT(*) as c FROM books GROUP BY format ORDER BY c DESC").fetchall()
        total_size = db.execute("SELECT COALESCE(SUM(size), 0) FROM books").fetchone()[0]
        self.send_json({
            "total_books": total,
            "total_categories": cats,
            "total_size_mb": round(total_size / 1048576, 1),
            "formats": {r["format"]: r["c"] for r in formats},
        })

    def _api_books(self, db, params):
        cat = params.get("category", [None])[0]
        search = params.get("q", [None])[0]
        limit = int(params.get("limit", [100])[0])
        offset = int(params.get("offset", [0])[0])

        if search:
            q = f"%{search}%"
            books = db.execute(
                "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY title LIMIT ? OFFSET ?",
                (q, q, limit, offset)
            ).fetchall()
        elif cat:
            books = db.execute(
                "SELECT * FROM books WHERE category = ? ORDER BY title LIMIT ? OFFSET ?",
                (cat, limit, offset)
            ).fetchall()
        else:
            books = db.execute("SELECT * FROM books ORDER BY title LIMIT ? OFFSET ?", (limit, offset)).fetchall()

        self.send_json([dict(b) for b in books])

    # ── Book Content API ─────────────────────────────────────────

    def _api_book_content(self, db, book_id):
        """Return book text content as JSON for the reader."""
        row = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if not row:
            self.send_error(404, "Book not found")
            return

        filepath = row["path"]
        content = ""

        try:
            if filepath.startswith("doomsday://"):
                # Fetch from Doomsday
                import urllib.request
                import html as html_mod
                doom_id = filepath.split("://")[1].split("/")[0]
                # Try chapters endpoint first
                try:
                    url = f"{DOOMSDAY_URL}/api/books/{doom_id}/chapters"
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        chapters = json.loads(resp.read())
                    # Fetch each chapter's text
                    parts = []
                    for ch in chapters:
                        ch_idx = ch.get("index", 0)
                        ch_title = ch.get("title", f"Chapter {ch_idx}")
                        try:
                            ch_url = f"{DOOMSDAY_URL}/api/books/{doom_id}/chapters/{ch_idx}/text"
                            with urllib.request.urlopen(ch_url, timeout=30) as resp:
                                ch_data = json.loads(resp.read())
                            ch_text = ch_data.get("text", "") if isinstance(ch_data, dict) else str(ch_data)
                            # Convert plain text to HTML paragraphs
                            ch_text = html_mod.escape(ch_text)
                            paras = ch_text.split("\n\n")
                            ch_html = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras if p.strip())
                            if not ch_html:
                                ch_html = f"<p>{ch_text.replace(chr(10), '<br>')}</p>"
                            parts.append(f"<h2 class='chapter-title'>{html_mod.escape(ch_title)}</h2>\n{ch_html}")
                        except Exception:
                            parts.append(f"<h2 class='chapter-title'>{html_mod.escape(ch_title)}</h2><p>[Could not load chapter]</p>")
                    content = "\n<hr class='chapter-break'>\n".join(parts)
                except Exception:
                    # Fallback: single chapter
                    try:
                        url = f"{DOOMSDAY_URL}/api/books/{doom_id}/chapters/0/text"
                        with urllib.request.urlopen(url, timeout=30) as resp:
                            ch_data = json.loads(resp.read())
                        ch_text = ch_data.get("text", "") if isinstance(ch_data, dict) else str(ch_data)
                        ch_text = html_mod.escape(ch_text)
                        paras = ch_text.split("\n\n")
                        content = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras if p.strip())
                    except Exception as e:
                        content = f"<p>Could not load content from Doomsday server: {e}</p>"

            elif row["format"] == ".txt":
                with open(filepath, "r", errors="replace") as f:
                    raw = f.read()
                # Convert plain text to paragraphs
                paras = raw.split("\n\n")
                content = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras if p.strip())

            elif row["format"] == ".pdf" and HAS_PYMUPDF:
                doc = fitz.open(filepath)
                parts = []
                for page_num in range(min(doc.page_count, 500)):
                    page = doc[page_num]
                    text = page.get_text()
                    if text.strip():
                        parts.append(f"<div class='pdf-page'><div class='page-num'>Page {page_num + 1}</div>{self._text_to_html(text)}</div>")
                doc.close()
                content = "\n<hr class='chapter-break'>\n".join(parts)

            elif row["format"] in (".epub",) and HAS_PYMUPDF:
                doc = fitz.open(filepath)
                parts = []
                for page_num in range(min(doc.page_count, 500)):
                    page = doc[page_num]
                    text = page.get_text()
                    if text.strip():
                        parts.append(self._text_to_html(text))
                doc.close()
                content = "\n".join(parts)
            else:
                content = f"<p style='text-align:center;padding:40px;color:#8b949e;'>This format ({row['format']}) is available for download but cannot be read in the browser.</p><p style='text-align:center;'><a href='/download/{book_id}' style='color:#00ff9f;'>Download Book</a></p>"

        except Exception as e:
            content = f"<p>Error loading book: {e}</p>"

        self.send_json({
            "id": book_id,
            "title": row["title"],
            "author": row["author"],
            "content": content,
        })

    @staticmethod
    def _text_to_html(text):
        """Convert plain text to HTML paragraphs."""
        import html as html_mod
        text = html_mod.escape(text)
        paras = text.split("\n\n")
        return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras if p.strip())

    # ── Reader UI ───────────────────────────────────────────────

    def _reader_ui(self, db, book):
        """Serve the page-turn reader interface, optimized for iPad."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>{book['title']} — N01D Reader</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,300;0,400;0,600;1,300;1,400&family=Inter:wght@400;500;600&display=swap');

:root {{
    --bg: #1a1a2e;
    --fg: #e0ddd5;
    --page-bg: #16213e;
    --accent: #00ff9f;
    --accent2: #00d4ff;
    --dim: #8b949e;
    --serif: 'Crimson Pro', 'Georgia', 'Times New Roman', serif;
    --sans: 'Inter', -apple-system, system-ui, sans-serif;
    --font-size: 19px;
    --line-height: 1.75;
    --page-padding: 48px;
    --header-h: 52px;
    --footer-h: 44px;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
html, body {{ height: 100%; overflow: hidden; background: var(--bg); color: var(--fg); }}

/* ── Header bar ── */
.reader-header {{
    position: fixed; top: 0; left: 0; right: 0; height: var(--header-h);
    background: rgba(10, 10, 20, 0.95); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(0, 255, 159, 0.15);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 20px; z-index: 100;
    transition: transform 0.3s ease;
}}
.reader-header.hidden {{ transform: translateY(-100%); }}
.reader-header .back {{ color: var(--accent2); text-decoration: none; font-family: var(--sans); font-size: 14px; display: flex; align-items: center; gap: 6px; }}
.reader-header .back:hover {{ color: var(--accent); }}
.reader-header .title-area {{ text-align: center; flex: 1; min-width: 0; }}
.reader-header .book-title {{ color: var(--fg); font-family: var(--sans); font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.reader-header .book-author {{ color: var(--dim); font-family: var(--sans); font-size: 11px; }}
.reader-header .controls {{ display: flex; align-items: center; gap: 8px; }}
.ctrl-btn {{
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
    color: var(--fg); border-radius: 8px; padding: 6px 12px; cursor: pointer;
    font-family: var(--sans); font-size: 13px; transition: all 0.2s;
}}
.ctrl-btn:hover {{ background: rgba(0, 255, 159, 0.12); border-color: var(--accent); color: var(--accent); }}
.ctrl-btn.active {{ background: var(--accent); color: #000; border-color: var(--accent); }}

/* ── Page container ── */
.reader-body {{
    position: fixed;
    top: var(--header-h); bottom: var(--footer-h); left: 0; right: 0;
    overflow: hidden;
}}

.page-container {{
    width: 100%; height: 100%;
    column-width: 100vw;
    column-gap: 0;
    column-fill: auto;
    overflow: hidden;
    font-family: var(--serif);
    font-size: var(--font-size);
    line-height: var(--line-height);
    color: var(--fg);
    padding: var(--page-padding);
    padding-bottom: 20px;
    transition: transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
    -webkit-user-select: none; user-select: none;
}}
.page-container p {{
    margin-bottom: 1em;
    text-align: justify;
    -webkit-hyphens: auto; hyphens: auto;
}}
.page-container h1, .page-container h2, .page-container h3 {{
    font-family: var(--sans);
    color: var(--accent2);
    margin: 1.2em 0 0.6em 0;
    line-height: 1.3;
}}
.page-container h1 {{ font-size: 1.6em; }}
.page-container h2 {{ font-size: 1.3em; }}
.page-container h3 {{ font-size: 1.1em; }}
.page-container .chapter-title {{
    color: var(--accent);
    font-size: 1.4em;
    text-align: center;
    padding: 20px 0;
    border-bottom: 1px solid rgba(0,255,159,0.2);
    margin-bottom: 1em;
}}
.page-container hr.chapter-break {{
    border: none;
    border-top: 1px solid rgba(0,255,159,0.15);
    margin: 2em 0;
}}
.page-container .pdf-page {{ margin-bottom: 2em; }}
.page-container .page-num {{
    text-align: center; color: var(--dim); font-family: var(--sans);
    font-size: 0.7em; margin-bottom: 0.5em;
}}
.page-container img {{ max-width: 100%; height: auto; border-radius: 4px; }}
.page-container blockquote {{
    border-left: 3px solid var(--accent2);
    padding-left: 1em; margin: 1em 0; font-style: italic;
    color: rgba(224, 221, 213, 0.8);
}}
.page-container pre, .page-container code {{
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    background: rgba(0,0,0,0.3); border-radius: 4px; padding: 2px 6px; font-size: 0.85em;
}}
.page-container pre {{ padding: 1em; overflow-x: auto; margin: 1em 0; }}

/* ── Touch zones (invisible) ── */
.touch-zone {{
    position: fixed; top: var(--header-h); bottom: var(--footer-h);
    z-index: 10; cursor: pointer;
}}
.touch-prev {{ left: 0; width: 30%; }}
.touch-next {{ right: 0; width: 30%; }}
.touch-center {{ left: 30%; width: 40%; }}

/* ── Page turn flash ── */
.page-flash {{
    position: fixed; top: var(--header-h); bottom: var(--footer-h);
    width: 100%; pointer-events: none; z-index: 5;
    opacity: 0; transition: opacity 0.15s ease;
}}
.page-flash.left {{ background: linear-gradient(to right, rgba(0,212,255,0.06) 0%, transparent 40%); }}
.page-flash.right {{ background: linear-gradient(to left, rgba(0,255,159,0.06) 0%, transparent 40%); }}
.page-flash.show {{ opacity: 1; }}

/* ── Footer ── */
.reader-footer {{
    position: fixed; bottom: 0; left: 0; right: 0; height: var(--footer-h);
    background: rgba(10, 10, 20, 0.95); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border-top: 1px solid rgba(0, 255, 159, 0.1);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 24px; z-index: 100; font-family: var(--sans);
    transition: transform 0.3s ease;
}}
.reader-footer.hidden {{ transform: translateY(100%); }}
.reader-footer .page-info {{ color: var(--dim); font-size: 12px; }}
.reader-footer .page-current {{ color: var(--accent); font-weight: 600; }}
.progress-bar {{
    flex: 1; margin: 0 20px; height: 3px;
    background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;
    cursor: pointer; position: relative;
}}
.progress-fill {{
    height: 100%; background: linear-gradient(90deg, var(--accent2), var(--accent));
    border-radius: 3px; transition: width 0.3s ease;
    box-shadow: 0 0 8px rgba(0, 255, 159, 0.3);
}}

/* ── Settings panel ── */
.settings-panel {{
    position: fixed; top: var(--header-h); right: 0;
    width: 280px; max-height: calc(100vh - var(--header-h) - var(--footer-h));
    background: rgba(16, 16, 32, 0.98); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border-left: 1px solid rgba(0,255,159,0.15); border-bottom: 1px solid rgba(0,255,159,0.15);
    border-radius: 0 0 0 12px;
    padding: 20px; z-index: 200;
    transform: translateX(100%); transition: transform 0.3s ease;
    overflow-y: auto;
}}
.settings-panel.open {{ transform: translateX(0); }}
.settings-panel h3 {{
    font-family: var(--sans); font-size: 13px; color: var(--accent);
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px;
}}
.setting-row {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px;
}}
.setting-row label {{ font-family: var(--sans); font-size: 13px; color: var(--dim); }}
.setting-row .btn-group {{ display: flex; gap: 4px; }}
.setting-row .btn-group button {{
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
    color: var(--fg); border-radius: 6px; padding: 5px 12px; cursor: pointer;
    font-family: var(--sans); font-size: 13px; transition: all 0.2s;
}}
.setting-row .btn-group button:hover {{ border-color: var(--accent); }}
.setting-row .btn-group button.active {{ background: var(--accent); color: #000; border-color: var(--accent); }}
.theme-btns button {{ width: 36px; height: 36px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.1); cursor: pointer; transition: all 0.2s; }}
.theme-btns button:hover {{ transform: scale(1.1); }}
.theme-btns .t-dark {{ background: #1a1a2e; }}
.theme-btns .t-sepia {{ background: #f4ecd8; }}
.theme-btns .t-light {{ background: #ffffff; }}
.theme-btns .t-midnight {{ background: #0d1117; }}
.theme-btns button.active {{ border-color: var(--accent); box-shadow: 0 0 10px rgba(0,255,159,0.3); }}

/* ── Loading ── */
.loading {{
    display: flex; align-items: center; justify-content: center;
    height: 100%; font-family: var(--sans); color: var(--dim);
    flex-direction: column; gap: 16px;
}}
.loading .spinner {{
    width: 40px; height: 40px; border: 3px solid rgba(0,255,159,0.15);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}

/* ── Theme: Sepia ── */
body.theme-sepia {{ --bg: #d4c5a9; --fg: #3d3427; --page-bg: #f4ecd8; --accent: #8b4513; --accent2: #654321; --dim: #8b7355; }}
body.theme-sepia .reader-header, body.theme-sepia .reader-footer, body.theme-sepia .settings-panel {{ background: rgba(212, 197, 169, 0.97); }}
body.theme-sepia .reader-header {{ border-bottom-color: rgba(139,69,19,0.2); }}
body.theme-sepia .reader-footer {{ border-top-color: rgba(139,69,19,0.2); }}

/* ── Theme: Light ── */
body.theme-light {{ --bg: #f5f5f5; --fg: #1a1a1a; --page-bg: #ffffff; --accent: #0066cc; --accent2: #0044aa; --dim: #666666; }}
body.theme-light .reader-header, body.theme-light .reader-footer, body.theme-light .settings-panel {{ background: rgba(245,245,245,0.97); }}
body.theme-light .reader-header {{ border-bottom-color: rgba(0,0,0,0.1); }}
body.theme-light .reader-footer {{ border-top-color: rgba(0,0,0,0.1); }}

/* ── Theme: Midnight ── */
body.theme-midnight {{ --bg: #0d1117; --fg: #c9d1d9; --page-bg: #0d1117; --accent: #00ff9f; --accent2: #58a6ff; --dim: #484f58; }}
body.theme-midnight .reader-header, body.theme-midnight .reader-footer, body.theme-midnight .settings-panel {{ background: rgba(13,17,23,0.97); }}

/* ── iPad specific ── */
@supports (padding-top: env(safe-area-inset-top)) {{
    .reader-header {{ padding-top: env(safe-area-inset-top); height: calc(var(--header-h) + env(safe-area-inset-top)); }}
    .reader-body {{ top: calc(var(--header-h) + env(safe-area-inset-top)); }}
    .touch-zone {{ top: calc(var(--header-h) + env(safe-area-inset-top)); }}
    .reader-footer {{ padding-bottom: env(safe-area-inset-bottom); height: calc(var(--footer-h) + env(safe-area-inset-bottom)); }}
    .reader-body {{ bottom: calc(var(--footer-h) + env(safe-area-inset-bottom)); }}
    .touch-zone {{ bottom: calc(var(--footer-h) + env(safe-area-inset-bottom)); }}
}}

@media (min-width: 768px) {{
    :root {{ --page-padding: 80px; --font-size: 20px; }}
}}
@media (min-width: 1024px) {{
    :root {{ --page-padding: 120px; --font-size: 21px; }}
}}
</style>
</head>
<body>

<div class="reader-header" id="readerHeader">
    <a href="/" class="back">\u25c0 Library</a>
    <div class="title-area">
        <div class="book-title">{book['title']}</div>
        <div class="book-author">{book['author']}</div>
    </div>
    <div class="controls">
        <button class="ctrl-btn" onclick="toggleSettings()" title="Settings">\u2699</button>
    </div>
</div>

<div class="settings-panel" id="settingsPanel">
    <h3>Reading Settings</h3>
    <div class="setting-row">
        <label>Font Size</label>
        <div class="btn-group">
            <button onclick="adjustFont(-1)">A\u2212</button>
            <button onclick="adjustFont(0)" style="font-weight:600">A</button>
            <button onclick="adjustFont(1)">A+</button>
        </div>
    </div>
    <div class="setting-row">
        <label>Font</label>
        <div class="btn-group" id="fontBtns">
            <button class="active" onclick="setFont('serif')">Serif</button>
            <button onclick="setFont('sans')">Sans</button>
            <button onclick="setFont('mono')">Mono</button>
        </div>
    </div>
    <div class="setting-row">
        <label>Line Spacing</label>
        <div class="btn-group">
            <button onclick="setLineHeight(1.5)">Tight</button>
            <button class="active" onclick="setLineHeight(1.75)">Normal</button>
            <button onclick="setLineHeight(2.0)">Loose</button>
        </div>
    </div>
    <div class="setting-row">
        <label>Theme</label>
        <div class="btn-group theme-btns">
            <button class="t-dark active" onclick="setTheme('dark')" title="Dark"></button>
            <button class="t-sepia" onclick="setTheme('sepia')" title="Sepia"></button>
            <button class="t-light" onclick="setTheme('light')" title="Light"></button>
            <button class="t-midnight" onclick="setTheme('midnight')" title="Midnight"></button>
        </div>
    </div>
</div>

<div class="reader-body" id="readerBody">
    <div class="loading" id="loadingState">
        <div class="spinner"></div>
        <div>Loading book\u2026</div>
    </div>
    <div class="page-container" id="pageContainer" style="display:none;"></div>
</div>

<div class="page-flash left" id="flashLeft"></div>
<div class="page-flash right" id="flashRight"></div>

<div class="touch-zone touch-prev" onclick="prevPage()" id="zonePrev"></div>
<div class="touch-zone touch-center" onclick="toggleChrome()"></div>
<div class="touch-zone touch-next" onclick="nextPage()" id="zoneNext"></div>

<div class="reader-footer" id="readerFooter">
    <div class="page-info">Page <span class="page-current" id="pageNum">1</span> of <span id="totalPages">1</span></div>
    <div class="progress-bar" id="progressBar" onclick="seekPage(event)">
        <div class="progress-fill" id="progressFill" style="width: 0%"></div>
    </div>
    <div class="page-info" id="percentage">0%</div>
</div>

<script>
const BOOK_ID = '{book['id']}';
let currentPage = 0;
let totalPages = 1;
let pageWidth = 0;
let chromeVisible = true;
let settingsOpen = false;
let fontSize = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--font-size'));
let touchStartX = 0;
let touchStartY = 0;
let touchStartTime = 0;
let isSwiping = false;

const container = document.getElementById('pageContainer');
const body = document.getElementById('readerBody');

// ── Load book content ──
async function loadBook() {{
    try {{
        const resp = await fetch(`/api/book/${{BOOK_ID}}/content`);
        const data = await resp.json();
        container.innerHTML = data.content || '<p>No content available.</p>';
        document.getElementById('loadingState').style.display = 'none';
        container.style.display = 'block';
        // Wait for render
        requestAnimationFrame(() => {{
            requestAnimationFrame(() => {{
                recalcPages();
                restorePosition();
            }});
        }});
    }} catch(e) {{
        document.getElementById('loadingState').innerHTML =
            `<div style="color:#ff6b6b;">\u2716 Failed to load book</div><div style="font-size:13px;margin-top:8px;">${{e.message}}</div>`;
    }}
}}

// ── Pagination ──
function recalcPages() {{
    pageWidth = body.clientWidth;
    // Set column width to match viewport
    container.style.columnWidth = pageWidth + 'px';
    container.style.width = pageWidth + 'px';
    container.style.height = body.clientHeight + 'px';

    const scrollW = container.scrollWidth;
    totalPages = Math.max(1, Math.round(scrollW / pageWidth));
    document.getElementById('totalPages').textContent = totalPages;

    if (currentPage >= totalPages) currentPage = totalPages - 1;
    goToPage(currentPage, false);
}}

function goToPage(n, animate = true) {{
    currentPage = Math.max(0, Math.min(n, totalPages - 1));
    const offset = -currentPage * pageWidth;
    container.style.transition = animate ? 'transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)' : 'none';
    container.style.transform = `translateX(${{offset}}px)`;
    updateProgress();
    savePosition();
}}

function nextPage() {{
    if (currentPage < totalPages - 1) {{
        goToPage(currentPage + 1);
        flashPage('right');
    }}
}}

function prevPage() {{
    if (currentPage > 0) {{
        goToPage(currentPage - 1);
        flashPage('left');
    }}
}}

function flashPage(dir) {{
    const el = dir === 'left' ? document.getElementById('flashLeft') : document.getElementById('flashRight');
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 200);
}}

function updateProgress() {{
    const pct = totalPages > 1 ? (currentPage / (totalPages - 1)) * 100 : 100;
    document.getElementById('pageNum').textContent = currentPage + 1;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('percentage').textContent = Math.round(pct) + '%';
}}

function seekPage(e) {{
    const bar = document.getElementById('progressBar');
    const rect = bar.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    goToPage(Math.round(pct * (totalPages - 1)));
}}

// ── Position memory ──
function savePosition() {{
    try {{ localStorage.setItem('n01d-pos-' + BOOK_ID, currentPage.toString()); }} catch(e) {{}}
}}
function restorePosition() {{
    try {{
        const saved = localStorage.getItem('n01d-pos-' + BOOK_ID);
        if (saved !== null) goToPage(parseInt(saved), false);
    }} catch(e) {{}}
}}

// ── Chrome toggle ──
function toggleChrome() {{
    chromeVisible = !chromeVisible;
    document.getElementById('readerHeader').classList.toggle('hidden', !chromeVisible);
    document.getElementById('readerFooter').classList.toggle('hidden', !chromeVisible);
    if (!chromeVisible && settingsOpen) toggleSettings();
    // Recalc after animation
    setTimeout(recalcPages, 350);
}}

function toggleSettings() {{
    settingsOpen = !settingsOpen;
    document.getElementById('settingsPanel').classList.toggle('open', settingsOpen);
}}

// ── Settings ──
function adjustFont(dir) {{
    if (dir === 0) fontSize = 19;
    else fontSize = Math.max(14, Math.min(28, fontSize + dir * 2));
    document.documentElement.style.setProperty('--font-size', fontSize + 'px');
    requestAnimationFrame(() => recalcPages());
}}

function setFont(f) {{
    const fonts = {{
        serif: "'Crimson Pro', 'Georgia', 'Times New Roman', serif",
        sans: "'Inter', -apple-system, system-ui, sans-serif",
        mono: "'JetBrains Mono', 'Fira Code', monospace"
    }};
    container.style.fontFamily = fonts[f] || fonts.serif;
    document.querySelectorAll('#fontBtns button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    requestAnimationFrame(() => recalcPages());
}}

function setLineHeight(lh) {{
    document.documentElement.style.setProperty('--line-height', lh);
    event.target.parentNode.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    requestAnimationFrame(() => recalcPages());
}}

function setTheme(t) {{
    document.body.className = t === 'dark' ? '' : 'theme-' + t;
    document.querySelectorAll('.theme-btns button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    try {{ localStorage.setItem('n01d-theme', t); }} catch(e) {{}}
}}

// ── Touch/Swipe (iPad) ──
document.addEventListener('touchstart', (e) => {{
    if (e.target.closest('.settings-panel') || e.target.closest('.reader-header')) return;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchStartTime = Date.now();
    isSwiping = false;
}}, {{ passive: true }});

document.addEventListener('touchmove', (e) => {{
    if (!touchStartX) return;
    const dx = e.touches[0].clientX - touchStartX;
    const dy = e.touches[0].clientY - touchStartY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 10) {{
        isSwiping = true;
        // Live drag feedback
        const offset = -currentPage * pageWidth + dx * 0.4;
        container.style.transition = 'none';
        container.style.transform = `translateX(${{offset}}px)`;
    }}
}}, {{ passive: true }});

document.addEventListener('touchend', (e) => {{
    if (!isSwiping) {{ touchStartX = 0; return; }}
    const dx = e.changedTouches[0].clientX - touchStartX;
    const elapsed = Date.now() - touchStartTime;
    const velocity = Math.abs(dx) / elapsed;

    // Swipe threshold: either fast flick or far enough
    if (dx < -50 || (dx < -20 && velocity > 0.4)) nextPage();
    else if (dx > 50 || (dx > 20 && velocity > 0.4)) prevPage();
    else goToPage(currentPage); // snap back

    touchStartX = 0;
    isSwiping = false;
}}, {{ passive: true }});

// ── Keyboard ──
document.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight' || e.key === ' ') {{ nextPage(); e.preventDefault(); }}
    else if (e.key === 'ArrowLeft') {{ prevPage(); e.preventDefault(); }}
    else if (e.key === 'Escape') {{ if (settingsOpen) toggleSettings(); else toggleChrome(); }}
}});

// ── Resize ──
let resizeTimer;
window.addEventListener('resize', () => {{
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(recalcPages, 200);
}});

// ── Init ──
(function init() {{
    // Restore theme
    try {{
        const saved = localStorage.getItem('n01d-theme');
        if (saved && saved !== 'dark') document.body.className = 'theme-' + saved;
    }} catch(e) {{}}
    loadBook();
}})();
</script>
</body>
</html>"""
        self.send_html(html)

    # ── Web UI ──────────────────────────────────────────────────

    def _web_ui(self, db):
        total = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        cats = db.execute("SELECT * FROM categories ORDER BY book_count DESC").fetchall()
        recent = db.execute("SELECT * FROM books ORDER BY date_added DESC LIMIT 20").fetchall()
        total_size = db.execute("SELECT COALESCE(SUM(size), 0) FROM books").fetchone()[0]

        cat_items = ""
        for c in cats:
            cat_items += f"""
            <a href="/opds/category/{quote(c['name'])}" class="cat-card">
                <span class="cat-count">{c['book_count']}</span>
                <span class="cat-name">{c['name']}</span>
            </a>"""

        book_rows = ""
        for b in recent:
            size_str = f"{b['size'] // 1024}KB" if b['size'] < 1048576 else f"{b['size'] / 1048576:.1f}MB"
            book_rows += f"""
            <tr>
                <td class="book-title"><a href="/read/{b['id']}">{b['title']}</a></td>
                <td>{b['author']}</td>
                <td><span class="badge">{b['category']}</span></td>
                <td>{b['format'].upper().strip('.')}</td>
                <td>{size_str}</td>
                <td><a href="/read/{b['id']}" class="read-btn" title="Read">📖</a> <a href="/download/{b['id']}" class="dl-btn" title="Download">⬇</a></td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>N01D Book Reader</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0d1117; color: #e6edf3; font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace; }}
.header {{ background: #0a0a0f; border-bottom: 1px solid #00ff9f33; padding: 20px 30px; display: flex; align-items: center; justify-content: space-between; }}
.header h1 {{ color: #00ff9f; font-size: 1.4em; text-shadow: 0 0 20px #00ff9f44; }}
.header .subtitle {{ color: #8b949e; font-size: 0.75em; margin-top: 4px; }}
.header .opds-url {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px 14px; color: #00d4ff; font-size: 0.8em; }}
.stats {{ display: flex; gap: 20px; padding: 20px 30px; border-bottom: 1px solid #21262d; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px 20px; flex: 1; text-align: center; }}
.stat .num {{ font-size: 1.8em; color: #00ff9f; font-weight: bold; text-shadow: 0 0 10px #00ff9f44; }}
.stat .label {{ color: #8b949e; font-size: 0.75em; margin-top: 4px; }}
.section {{ padding: 20px 30px; }}
.section h2 {{ color: #00d4ff; font-size: 1.1em; margin-bottom: 15px; border-bottom: 1px solid #21262d; padding-bottom: 8px; }}
.categories {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }}
.cat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; text-decoration: none; color: #e6edf3; display: flex; flex-direction: column; align-items: center; gap: 6px; transition: all 0.2s; }}
.cat-card:hover {{ border-color: #00ff9f; background: #21262d; box-shadow: 0 0 15px #00ff9f22; }}
.cat-count {{ font-size: 1.6em; color: #a371f7; font-weight: bold; }}
.cat-name {{ font-size: 0.75em; color: #8b949e; text-align: center; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 10px 12px; border-bottom: 2px solid #30363d; color: #00ff9f; font-size: 0.8em; text-transform: uppercase; }}
td {{ padding: 10px 12px; border-bottom: 1px solid #21262d; font-size: 0.85em; }}
tr:hover {{ background: #161b22; }}
.book-title a {{ color: #00d4ff; text-decoration: none; }}
.book-title a:hover {{ text-decoration: underline; text-shadow: 0 0 8px #00d4ff44; }}
.badge {{ background: #21262d; border: 1px solid #30363d; border-radius: 12px; padding: 2px 10px; font-size: 0.75em; color: #a371f7; }}
.dl-btn {{ color: #00ff9f; text-decoration: none; font-size: 1.2em; }}
.dl-btn:hover {{ text-shadow: 0 0 10px #00ff9f; }}
.read-btn {{ color: #00d4ff; text-decoration: none; font-size: 1.1em; }}
.read-btn:hover {{ text-shadow: 0 0 10px #00d4ff; }}
.search-bar {{ display: flex; gap: 10px; margin-bottom: 20px; }}
.search-bar input {{ flex: 1; background: #0a0a0f; border: 1px solid #30363d; border-radius: 6px; padding: 10px 14px; color: #e6edf3; font-family: inherit; font-size: 0.9em; outline: none; }}
.search-bar input:focus {{ border-color: #00ff9f; box-shadow: 0 0 10px #00ff9f22; }}
.search-bar button {{ background: #00ff9f22; border: 1px solid #00ff9f; color: #00ff9f; border-radius: 6px; padding: 10px 20px; cursor: pointer; font-family: inherit; }}
.search-bar button:hover {{ background: #00ff9f33; }}
.scan-btn {{ background: #a371f722; border: 1px solid #a371f7; color: #a371f7; border-radius: 6px; padding: 8px 16px; cursor: pointer; font-family: inherit; font-size: 0.8em; }}
.scan-btn:hover {{ background: #a371f733; }}
.footer {{ text-align: center; padding: 20px; color: #6e7681; font-size: 0.7em; border-top: 1px solid #21262d; margin-top: 20px; }}
</style>
</head>
<body>
<div class="header">
    <div>
        <h1>📚 N01D Book Reader</h1>
        <div class="subtitle">NullSec Self-Hosted eBook Library & OPDS Server</div>
    </div>
    <div style="text-align: right">
        <div class="opds-url">OPDS: http://{{host}}:8074/opds</div>
        <div style="margin-top: 6px;"><button class="scan-btn" onclick="rescan()">↻ Rescan Library</button></div>
    </div>
</div>

<div class="stats">
    <div class="stat"><div class="num">{total}</div><div class="label">Total Books</div></div>
    <div class="stat"><div class="num">{len(cats)}</div><div class="label">Categories</div></div>
    <div class="stat"><div class="num">{total_size / 1048576:.0f} MB</div><div class="label">Library Size</div></div>
</div>

<div class="section">
    <h2>⬡ Categories</h2>
    <div class="categories">{cat_items}</div>
</div>

<div class="section">
    <h2>⬡ Recently Added</h2>
    <div class="search-bar">
        <input type="text" id="search" placeholder="Search books..." onkeydown="if(event.key==='Enter')searchBooks()">
        <button onclick="searchBooks()">Search</button>
    </div>
    <table>
        <thead><tr><th>Title</th><th>Author</th><th>Category</th><th>Format</th><th>Size</th><th></th></tr></thead>
        <tbody id="bookTable">{book_rows}</tbody>
    </table>
</div>

<div class="footer">
    N01D Book Reader • NullSec Toolkit • OPDS endpoint: /opds
</div>

<script>
function rescan() {{
    fetch('/api/scan').then(r => r.json()).then(d => {{
        alert('Scan complete: ' + d.total + ' books in library');
        location.reload();
    }});
}}
function searchBooks() {{
    const q = document.getElementById('search').value;
    fetch('/api/books?q=' + encodeURIComponent(q)).then(r => r.json()).then(books => {{
        const tbody = document.getElementById('bookTable');
        tbody.innerHTML = books.map(b => {{
            const size = b.size < 1048576 ? Math.floor(b.size/1024)+'KB' : (b.size/1048576).toFixed(1)+'MB';
            return '<tr><td class="book-title"><a href="/read/'+b.id+'">'+b.title+'</a></td><td>'+b.author+'</td><td><span class="badge">'+b.category+'</span></td><td>'+b.format.toUpperCase().replace('.','')+'</td><td>'+size+'</td><td><a href="/read/'+b.id+'" class="read-btn" title="Read">📖</a> <a href="/download/'+b.id+'" class="dl-btn" title="Download">⬇</a></td></tr>';
        }}).join('');
    }});
}}
</script>
</body>
</html>""".replace("{{host}}", self.headers.get("Host", "localhost:8074").split(":")[0])
        self.send_html(html)


# ─── Background Scanner ────────────────────────────────────────

def background_scanner(config):
    """Periodically rescan library directories."""
    interval = config.get("scan_interval_minutes", 30) * 60
    while True:
        time.sleep(interval)
        try:
            db = sqlite3.connect(DB_FILE)
            scan_library(config, db)
            db.close()
        except Exception as e:
            print(f"  [!] Background scan error: {e}")


# ─── Main ──────────────────────────────────────────────────────

def main():
    print("""
    ╔══════════════════════════════════════════════╗
    ║  N01D Book Reader - OPDS Library Server      ║
    ║  Part of the NullSec Toolkit                 ║
    ╚══════════════════════════════════════════════╝
    """)

    config = load_config()

    # Ensure cover cache directory
    os.makedirs(config["cover_cache_dir"], exist_ok=True)

    # Initialize database and scan
    db = init_db()
    scan_library(config, db)
    db.close()

    # Start background scanner
    scanner_thread = threading.Thread(target=background_scanner, args=(config,), daemon=True)
    scanner_thread.start()

    # Start HTTP server
    host = config["host"]
    port = config["port"]
    server = HTTPServer((host, port), N01DBookHandler)

    print(f"""
    [✓] Server running!
    [✓] Web UI:    http://localhost:{port}/
    [✓] OPDS Feed: http://localhost:{port}/opds
    [✓] LAN OPDS:  http://{{LAN_IP}}:{port}/opds

    iPad/Mobile Setup:
      1. Open your OPDS reader app
      2. Add catalog: http://YOUR_IP:{port}/opds
      3. Browse & download books!

    Press Ctrl+C to stop.
    """)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  [*] Shutting down N01D Book Reader...")
        server.shutdown()


if __name__ == "__main__":
    main()
