# 📚 N01D Book Reader

**Self-Hosted eBook Library & OPDS Server**

[![NullSec](https://img.shields.io/badge/NullSec-Toolkit-red?style=flat-square)](https://github.com/bad-antics)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

Part of the [NullSec Toolkit](https://github.com/bad-antics) — a zero-dependency Python eBook server with OPDS catalog support for any reader app (iPad, Android, Kindle, etc.).

```
███╗   ██╗ ██████╗  ██╗██████╗       ██████╗  ██████╗  ██████╗ ██╗  ██╗
████╗  ██║██╔═████╗███║██╔══██╗      ██╔══██╗██╔═══██╗██╔═══██╗██║ ██╔╝
██╔██╗ ██║██║██╔██║╚██║██║  ██║█████╗██████╔╝██║   ██║██║   ██║█████╔╝
██║╚██╗██║████╔╝██║ ██║██║  ██║╚════╝██╔══██╗██║   ██║██║   ██║██╔═██╗
██║ ╚████║╚██████╔╝ ██║██████╔╝      ██████╔╝╚██████╔╝╚██████╔╝██║  ██╗
╚═╝  ╚═══╝ ╚═════╝  ╚═╝╚═════╝       ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
```

## Features

- 📖 **OPDS Catalog Server** — Compatible with any OPDS reader (KOReader, Librera, Moon+ Reader, Panels, etc.)
- 🌐 **Web Interface** — Browse, search, and read books from any browser
- 📁 **Multi-Format Support** — PDF, EPUB, MOBI, AZW3, CBZ, CBR, FB2, DJVU, TXT
- 🔍 **Full-Text Search** — Search by title, author, or category
- 🏷️ **Auto-Categorization** — Automatically categorizes books by genre/topic
- 🖼️ **Cover Extraction** — Extracts and caches book cover images
- 🔄 **Network Sync** — Sync from remote book servers (Doomsday, Calibre, etc.)
- 🛡️ **Zero Dependencies** — Pure Python 3 standard library (PyMuPDF optional for PDF covers)
- 🐧 **Systemd Service** — Runs as a background service on Linux

## Quick Start

```bash
# Clone
git clone https://github.com/bad-antics/n01d-book-reader.git
cd n01d-book-reader

# Run
python3 n01d-book-reader.py

# Access
# Web UI: http://localhost:8074
# OPDS:   http://localhost:8074/opds
```

## Configuration

Edit `config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8074,
  "library_name": "N01D Book Reader",
  "library_dirs": [
    "/home/user/Books",
    "/home/user/Documents"
  ],
  "supported_formats": [".pdf", ".epub", ".mobi", ".azw3", ".cbz", ".cbr", ".fb2", ".djvu", ".txt"],
  "scan_interval_minutes": 30
}
```

## OPDS Setup

Add this OPDS feed URL to your reader app:

```
http://<your-ip>:8074/opds
```

### Tested Readers

| App | Platform | Status |
|-----|----------|--------|
| KOReader | Linux/Android | ✅ |
| Librera Reader | Android | ✅ |
| Moon+ Reader | Android | ✅ |
| Panels | iOS/iPadOS | ✅ |
| Chunky Reader | iOS | ✅ |
| Aldiko | Android | ✅ |

## Remote Sync

Sync books from a remote server (e.g., Windows machine running a book server):

```bash
# Edit DOOMSDAY_URL in sync_doomsday.py
python3 sync_doomsday.py
```

## Systemd Service

```bash
# Install service
sudo cp n01d-book-reader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now n01d-book-reader

# Check status
sudo systemctl status n01d-book-reader
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI |
| `GET /opds` | OPDS root catalog |
| `GET /opds/all` | All books feed |
| `GET /opds/search?q=` | Search books |
| `GET /opds/category/<name>` | Books by category |
| `GET /api/books` | JSON book list |
| `GET /api/stats` | Library statistics |
| `GET /download/<id>` | Download book file |
| `GET /cover/<id>` | Book cover image |

## Part of NullSec

- [NullSec Linux](https://github.com/bad-antics/nullsec-linux) — Security-focused Linux distribution
- [N01D Forge](https://github.com/bad-antics/n01d-forge) — Security toolkit builder
- [N01D Machine](https://github.com/bad-antics/n01d-machine) — Automated security lab
- [Marshall](https://github.com/bad-antics/marshall) — OSINT browser extensions
- [NullSec LogReaper](https://github.com/bad-antics/nullsec-logreaper) — Log analysis & threat detection

## License

MIT License — See [LICENSE](LICENSE) for details.
