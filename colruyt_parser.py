"""Parser for Colruyt receipts (PDF with a text layer).

Uses poppler's `pdftotext -layout`, which keeps the column layout of the
receipt, then pulls out the article lines with regular expressions.
"""
from __future__ import annotations

import re
import subprocess
from decimal import Decimal
from pathlib import Path

# A   4680 BONI yoghurt zwarte kers 200g     3    1,05    3,15
# A   8099 BONI appel jonagold 6st     0,931kg 1,42    1,32
ITEM_RE = re.compile(
    r"^\s*(?P<vat>[A-Z])\s+(?P<art>\d{2,7})\s+(?P<name>.+?)\s{2,}"
    r"(?:(?P<deposit>-?\d+,\d{2})\s+)?"
    r"(?P<qty>-?\d+(?:,\d+)?)(?P<unit>kg)?\s+"
    r"(?P<unit_price>-?\d+,\d+)\s+(?P<amount>-?\d+,\d{2})\s*$"
)
# Discount / promotion lines without an article number, ending in a negative amount
DISCOUNT_RE = re.compile(r"^\s*(?P<name>[^\d\s].*?)\s{2,}.*?(?P<amount>-\d+,\d{2})\s*$")
TOTAL_RE = re.compile(r"Totaal betaald\s+€\s+(?P<total>-?\d+,\d{2})")
TE_BETALEN_RE = re.compile(r"TE BETALEN.*\n.*€\s*(?P<total>-?\d+,\d{2})\s*$", re.M)
DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")


def _num(s: str) -> Decimal:
    return Decimal(s.replace(",", "."))


def pdf_to_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def parse_text(text: str) -> dict:
    items = []
    in_items = False
    for line in text.splitlines():
        if "Art.Nr" in line:
            in_items = True
            continue
        if not in_items:
            continue
        if "TOTAAL GOEDEREN" in line or "TE BETALEN" in line:
            break
        m = ITEM_RE.match(line)
        if m:
            items.append({
                "article": m["art"],
                "name": re.sub(r"\s+", " ", m["name"]).strip(),
                "quantity": m["qty"] + (m["unit"] or ""),
                "unit_price": str(_num(m["unit_price"])),
                "amount": str(_num(m["amount"])),
            })
            continue
        d = DISCOUNT_RE.match(line)
        if d:
            items.append({
                "article": "",
                "name": re.sub(r"\s+", " ", d["name"]).strip(),
                "quantity": "",
                "unit_price": "",
                "amount": str(_num(d["amount"])),
            })

    total = None
    for rx in (TOTAL_RE, TE_BETALEN_RE):
        if (m := rx.search(text)):
            total = str(_num(m["total"]))
            break

    date = DATE_RE.search(text)
    item_sum = sum((Decimal(i["amount"]) for i in items), Decimal("0"))
    return {
        "date": f"{date[1]} {date[2]}" if date else None,
        "items": items,
        "items_total": str(item_sum),
        "receipt_total": total,
        "total_matches": total is not None and Decimal(total) == item_sum,
    }


def parse_pdf(path: Path) -> dict:
    result = parse_text(pdf_to_text(path))
    result["file"] = path.name
    return result


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse_pdf(Path(sys.argv[1])), indent=2, ensure_ascii=False))
