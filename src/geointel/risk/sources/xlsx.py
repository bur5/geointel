"""Minimal .xlsx reader (standard library only): sheets as lists of rows of strings."""

import io
import re
import zipfile
from xml.etree import ElementTree

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheets(payload: bytes) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        book = ElementTree.fromstring(z.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        out: dict[str, list[list[str]]] = {}
        for sheet in book.find("m:sheets", NS):
            target = targets.get(sheet.get(REL), "")
            path = "xl/" + target.lstrip("/").removeprefix("xl/")
            if path not in z.namelist():
                continue
            root = ElementTree.fromstring(z.read(path))
            rows = []
            for row in root.iter(f"{{{NS['m']}}}row"):
                cells: dict[int, str] = {}
                for c in row.findall("m:c", NS):
                    v = c.find("m:v", NS)
                    text = ""
                    if c.get("t") == "s" and v is not None:
                        text = shared[int(v.text)]
                    elif c.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                    elif v is not None:
                        text = v.text or ""
                    cells[_col(c.get("r", "A1"))] = text
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            out[sheet.get("name", "")] = rows
        return out
