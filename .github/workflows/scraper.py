#!/usr/bin/env python3
"""
Každých 10 s načíta zastávkovú tabuľu imhd.sk (Homolova, st=85), nájde
PRVÝ riadok zhora, ktorý obsahuje slovo "Petržalka", a zapíše ho do index.html.
Voliteľne zmeny pushne do git repozitára (PUBLISH_DIR).

Použitie:
  pip install playwright && playwright install chromium
  python scraper.py                 # beží donekonečna
  DURATION=280 python scraper.py    # beží 280 s (pre GitHub Actions)
  PUBLISH_DIR=./live python scraper.py   # + git commit/push po každom behu
"""
import html
import os
import subprocess
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

URL = "https://imhd.sk/ba/online-zastavkova-tabula?st=85"
KEYWORD = "petrzalka"
INTERVAL = 10
DURATION = int(os.getenv("DURATION", "0"))  # 0 = nekonečne
OUT_DIR = Path(os.getenv("PUBLISH_DIR", "."))


def norm(s: str) -> str:
    """Bez diakritiky a malé písmená -> 'Petržalka' == 'petrzalka'."""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def fetch_first_row(page) -> str:
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    # počkaj, kým sa tabuľka naplní (alebo objaví "Žiadne plánované odchody")
    try:
        page.wait_for_function(
            """() => [...document.querySelectorAll('table tr')]
                   .some(r => r.innerText.trim().length > 3 && !/^Linka/.test(r.innerText.trim()))""",
            timeout=15000,
        )
    except Exception:
        pass
    rows = page.eval_on_selector_all(
        "table tr",
        "els => els.map(e => [...e.querySelectorAll('td,th')].map(c => c.innerText.trim()).filter(Boolean).join(' | '))",
    )
    for row in rows:  # poradie zhora nadol
        if KEYWORD in norm(row):
            return row
    return ""


def write_html(row: str):
    now = datetime.now(ZoneInfo("Europe/Bratislava")).strftime("%d.%m.%Y %H:%M:%S")
    body = html.escape(row) if row else "Žiadny odchod smerom Petržalka"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(
        f"""<!doctype html>
<html lang="sk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
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
    start = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        while True:
            t0 = time.time()
            try:
                row = fetch_first_row(page)
                write_html(row)
                publish()
                print(datetime.now().isoformat(timespec="seconds"), row or "(nič)", flush=True)
            except Exception as e:
                print("Chyba:", e, flush=True)
            if DURATION and time.time() - start + INTERVAL > DURATION:
                break
            time.sleep(max(0, INTERVAL - (time.time() - t0)))
        browser.close()


if __name__ == "__main__":
    main()
