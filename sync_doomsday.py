#!/usr/bin/env python3
"""
N01D Book Reader - Doomsday Sync
Imports the book catalog from the Doomsday Windows machine
and proxies downloads + covers through the local instance.
"""

import json
import hashlib
import sqlite3
import urllib.request
import sys
import os
import time

DOOMSDAY_URL = "http://192.168.40.22:8074"
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")
COVERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covers")
TAGS_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doomsday_tags.json")


def fetch_json(url, timeout=120):
    """Fetch JSON from a URL."""
    print(f"  [>] Fetching {url}...")
    sys.stdout.flush()
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_tags():
    """Fetch tags from Doomsday and build a mapping."""
    tags = fetch_json(f"{DOOMSDAY_URL}/api/tags")
    tag_map = {t["id"]: t["name"] for t in tags}
    with open(TAGS_CACHE, "w") as f:
        json.dump(tags, f, indent=2)
    print(f"  [✓] Got {len(tags)} tags/categories")
    return tag_map


def fetch_book_tags(book_id):
    """Try to get tags for a specific book."""
    try:
        data = fetch_json(f"{DOOMSDAY_URL}/api/books/{book_id}")
        return data.get("tags", [])
    except Exception:
        return []


def sync_books():
    """Sync the full book catalog from Doomsday into the local database."""
    print("=" * 60)
    print("  N01D Book Reader — Doomsday Sync")
    print("=" * 60)
    print()

    os.makedirs(COVERS_DIR, exist_ok=True)

    # Fetch tag mapping
    tag_map = fetch_tags()

    # Fetch all books
    print(f"  [>] Fetching book catalog from {DOOMSDAY_URL}...")
    sys.stdout.flush()
    books = fetch_json(f"{DOOMSDAY_URL}/api/books?limit=5000")
    print(f"  [✓] Got {len(books)} books from Doomsday")

    # Open local database
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")

    # Ensure table exists
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

    # Import books
    imported = 0
    skipped = 0
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    for i, book in enumerate(books):
        # Create a unique local ID based on doomsday ID
        local_id = f"doomsday_{book['id']}"
        # Use the doomsday path as a virtual path
        virtual_path = f"doomsday://{book['id']}/{book.get('path', 'unknown')}"

        # Check if already imported
        existing = conn.execute("SELECT id FROM books WHERE id = ?", (local_id,)).fetchone()
        if existing:
            skipped += 1
            continue

        title = book.get("title", "Unknown")
        author = book.get("author", "Unknown")
        has_epub = book.get("has_epub", False)
        fmt = ".epub" if has_epub else ".unknown"

        # Try to determine category from the path or title
        category = categorize_doomsday_book(title, author, book.get("path", ""))

        try:
            conn.execute("""
                INSERT OR IGNORE INTO books (id, title, author, path, format, size, category, description, date_added, date_modified, language, pages)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                local_id, title, author, virtual_path, fmt,
                0, category, "", now, now, "en", 0
            ))
            imported += 1
        except sqlite3.IntegrityError:
            skipped += 1

        if (i + 1) % 100 == 0:
            print(f"  [>] Processed {i + 1}/{len(books)}...")
            sys.stdout.flush()
            conn.commit()

    conn.commit()

    # Update category counts
    conn.execute("DELETE FROM categories")
    cats = conn.execute("SELECT category, COUNT(*) FROM books GROUP BY category ORDER BY category").fetchall()
    for cat, count in cats:
        conn.execute("INSERT OR REPLACE INTO categories (name, book_count) VALUES (?, ?)", (cat, count))
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    conn.close()

    print()
    print(f"  [✓] Imported: {imported} new books")
    print(f"  [✓] Skipped:  {skipped} (already in library)")
    print(f"  [✓] Total:    {total} books in local library")
    print()


def categorize_doomsday_book(title: str, author: str, path: str) -> str:
    """Categorize a book based on title, author, and path."""
    combined = f"{title} {author} {path}".lower()
    categories = {
        "Philosophy": ["philosophy", "nietzsche", "plato", "aristotle", "socrates", "kant", "hegel", "marx", "existential", "metaphysic", "baudrillard", "foucault", "deleuze", "derrida", "sartre", "camus", "kierkegaard", "schopenhauer", "wittgenstein", "heidegger", "phenomenolog"],
        "Science": ["science", "physics", "chemistry", "biology", "quantum", "relativity", "evolution", "darwin", "einstein", "cosmolog", "astrono", "mathemat", "theorem"],
        "History": ["history", "ancient", "medieval", "empire", "dynasty", "civilization", "revolution", "war of", "world war", "civil war", "colonial", "conquest"],
        "Warfare & Military": ["warfare", "military", "strategy", "tactics", "battle", "weapon", "army", "navy", "general", "soldier", "combat", "guerrilla", "insurgent"],
        "Gothic Horror": ["gothic", "horror", "lovecraft", "poe", "shelley", "dracula", "frankenstein", "supernatural", "occult", "dark", "macabre", "weird tale"],
        "Science Fiction": ["sci-fi", "science fiction", "dystop", "utopi", "cyberpunk", "space", "robot", "android", "future", "asimov", "clarke", "dick, philip", "bradbury", "verne"],
        "Fiction": ["novel", "fiction", "story", "stories", "tales", "romance", "adventure", "mystery", "detective", "thriller"],
        "Poetry": ["poem", "poetry", "verse", "sonnet", "ballad", "ode"],
        "Political Theory": ["politic", "government", "democracy", "republic", "anarch", "communi", "sociali", "capital", "libert", "totalitar", "authoritar", "propaganda", "machiavelli"],
        "Occult & Esoteric": ["occult", "esoteric", "magic", "alchemy", "hermet", "kabbal", "mystici", "theosoph", "gnostic", "tarot", "astrology", "ritual"],
        "Psychology": ["psychology", "psycholog", "freud", "jung", "behavior", "conscious", "unconscious", "neurosis", "psychoanaly", "cognitive"],
        "Technology": ["technolog", "computer", "program", "hacking", "cyber", "encrypt", "network", "artificial intelligence", "machine learning"],
        "Religion & Mythology": ["religio", "bible", "quran", "buddhis", "hindu", "christian", "islam", "mytholog", "god", "divine", "sacred", "spiritual", "theolog"],
        "Art & Literature": ["art", "painting", "sculpture", "literature", "literary", "criticism", "aesthetic", "beauty"],
        "Economics": ["econom", "market", "trade", "wealth", "poverty", "capitali", "finance", "monetary"],
        "Biography": ["biography", "autobiograph", "memoir", "life of", "letters of"],
    }

    for cat, keywords in categories.items():
        if any(kw in combined for kw in keywords):
            return cat
    return "General Literature"


if __name__ == "__main__":
    sync_books()
