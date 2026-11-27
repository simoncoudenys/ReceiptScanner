"""Colruyt receipt splitter — tiny stdlib web server.

Run:  python3 app.py   then open http://localhost:8000
The user imports a receipt PDF in the browser (POST /api/import).
GET /api/receipt still reads the single PDF in ./in.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from colruyt_parser import parse_pdf

ROOT = Path(__file__).parent
IN_DIR = Path(os.environ.get("RECEIPT_IN_DIR", ROOT / "in"))
INDEX = ROOT / "static" / "index.html"
HOST = os.environ.get("RECEIPT_HOST", "127.0.0.1")
PORT = int(os.environ.get("RECEIPT_PORT", "8000"))
MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB


def parse_upload(data: bytes, filename: str) -> dict:
    """Parse an uploaded receipt PDF. Raises ValueError with a user-facing message."""
    if not data.startswith(b"%PDF"):
        raise ValueError("That file is not a PDF.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipt.pdf"
        path.write_bytes(data)
        try:
            receipt = parse_pdf(path)
        except subprocess.CalledProcessError:
            raise ValueError("Could not read this PDF. Is it damaged?") from None
        except FileNotFoundError:
            raise RuntimeError("pdftotext (poppler-utils) is not installed on the server.") from None
    if not receipt["items"]:
        raise ValueError("No items found in this PDF. Is it a Colruyt receipt?")
    receipt["file"] = filename
    return receipt


def load_receipt() -> dict:
    pdfs = sorted(IN_DIR.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found in {IN_DIR}")
    if len(pdfs) > 1:
        print(f"Warning: {len(pdfs)} PDFs in {IN_DIR}, using {pdfs[0].name}")
    return parse_pdf(pdfs[0])


def split(items: list[dict], participants: list[str], assignments: list[list[str]]) -> dict:
    """Split each item equally (in cents) among its assignees.

    Leftover cents go to the first assignees, so totals always add up exactly.
    """
    totals = {p: 0 for p in participants}
    lines = {p: [] for p in participants}
    unassigned = []
    for item, people in zip(items, assignments):
        people = [p for p in people if p in totals]
        cents = int(Decimal(item["amount"]) * 100)
        if not people:
            unassigned.append(item)
            continue
        base, rest = divmod(cents, len(people))
        for i, p in enumerate(people):
            share = base + (1 if i < rest else 0)
            totals[p] += share
            lines[p].append({
                "name": item["name"],
                "amount": item["amount"],
                "shared_with": len(people),
                "share": f"{share / 100:.2f}",
            })
    return {
        "people": [
            {"name": p, "total": f"{totals[p] / 100:.2f}", "items": lines[p]}
            for p in participants
        ],
        "grand_total": f"{sum(totals.values()) / 100:.2f}",
        "unassigned": unassigned,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/receipt":
            try:
                self._json(load_receipt())
            except Exception as e:  # surface parse errors in the UI
                self._json({"error": str(e)}, 500)
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        if self.path not in ("/api/import", "/api/split"):
            return self._send(404, b"Not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_UPLOAD:
            return self._json({"error": "File too large (max 10 MB)."}, 413)
        body = self.rfile.read(length)

        if self.path == "/api/import":
            name = unquote(self.headers.get("X-Filename", "receipt.pdf"))
            try:
                self._json(parse_upload(body, name))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # e.g. pdftotext not installed
                self._json({"error": str(e)}, 500)
        else:
            payload = json.loads(body or b"{}")
            self._json(split(payload["items"], payload["participants"], payload["assignments"]))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Receipt splitter running on http://{HOST}:{PORT} (reading {IN_DIR})", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
