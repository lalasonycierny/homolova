#!/usr/bin/env python3
"""
Načíta zastávkovú tabuľu imhd.sk (Homolova, st=85), nájde
PRVÝ riadok zhora, ktorý obsahuje slovo "Petržalka", a zapíše ho do index.html.
Voliteľne zmeny pushne do git repozitára (PUBLISH_DIR).

Použitie:
  pip install playwright && playwright install chromium
  python scraper.py                 # beží donekonečna
  RUNS=10 INTERVAL=30 python scraper.py   # 10 behov po 30 s (pre GitHub Actions)
  PUBLISH_DIR=./live python scraper.py   # + git commit/push po každom behu
"""
import html
import os
import re
import subprocess
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

URL = "https://imhd.sk/ba/online-zastavkova-tabula?st=85"
KEYWORD = "petrzalka"
INTERVAL = int(os.getenv("INTERVAL", "30"))  # pauza medzi behmi v sekundách
RUNS = int(os.getenv("RUNS", "0"))  # počet behov, 0 = nekonečne
OUT_DIR = Path(os.getenv("PUBLISH_DIR", "."))


def norm(s: str) -> str:
    """Bez diakritiky a malé písmená -> 'Petržalka' == 'petrzalka'."""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# riadky, ktoré sú len popisy pre čítačky obrazovky - do výstupu ich nedávame
SKIP = ("linka ", "smer ", "odchod ", "plánovaný odchod", "nástupište ")


def parse_rows(text: str):
    """Rozdelí text stránky na odchody. Každý odchod začína riadkom 'Linka <číslo>'."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows, cur = [], None
    for l in lines:
        if re.match(r"^Linka \d+", l):
            cur = []
            rows.append(cur)
        elif cur is not None:
            cur.append(l)
    return rows


def fetch_first_row(page) -> str:
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    # počkaj, kým sa objavia odchody
    try:
        page.wait_for_function(
            "() => /\\d+\\s*min|●|~\\d/.test(document.body.innerText)", timeout=20000
        )
    except Exception:
        pass
    page.wait_for_timeout(1000)
    text = page.evaluate("() => document.body.innerText")
    for row in parse_rows(text):  # poradie zhora nadol
        if KEYWORD in norm(" ".join(row)):
            parts = [l for l in row if not l.lower().startswith(SKIP)]
            # číslo linky pridáme zo začiatku, ak v čistých dieloch chýba
            return " | ".join(parts)
    return ""


def write_html(row: str):
    now = datetime.now(ZoneInfo("Europe/Bratislava")).strftime("%d.%m.%Y %H:%M:%S")
    body = html.escape(row) if row else "Žiadny odchod smerom Petržalka"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(
        f"""<!doctype html>
<html lang="sk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{INTERVAL}">
<title>Homolova → Petržalka</title>
<style>body{{font-family:system-ui,sans-serif;background:#111;color:#fff;
display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;margin:0}}
h1{{font-size:8vw}} small{{color:#aaa}}</style></head>
<body><h1>{body}</h1><small>Aktualizované: {now}</small></body></html>
""",
        encoding="utf-8",
    )


def publish():
    if "PUBLISH_DIR" not in os.environ:
        return
    run = lambda *a: subprocess.run(a, cwd=OUT_DIR, check=False, capture_output=True)
    run("git", "add", "index.html")
    # amend + force push: história repozitára nenarastá
    if run("git", "rev-parse", "HEAD").returncode == 0:
        run("git", "commit", "--amend", "-m", "live", "--allow-empty")
    else:
        run("git", "commit", "-m", "live", "--allow-empty")
    run("git", "push", "--force", "origin", "HEAD:live")


def main():
    count = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        while True:
            t0 = time.time()
            try:
                row = fetch_first_row(page)
                write_html(row)
                publish()
                print(datetime.now().isoformat(timespec="seconds"), row or "(nič)", flush=True)
            except Exception as e:
                print("Chyba:", e, flush=True)
            count += 1
            if RUNS and count >= RUNS:
                break
            time.sleep(max(0, INTERVAL - (time.time() - t0)))
        browser.close()


if __name__ == "__main__":
    main()
