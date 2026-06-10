"""
Download UPSC Prelims and Mains question paper PDFs from Rau's IAS Compass.

Usage:
    python -m app.ai.training.scrape_upsc_papers [--prelims] [--mains] [--all]
"""

import asyncio
import logging
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("scrape_upsc")

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = DATA_DIR / "raw"
RAU_BASE = "https://compass.rauias.com"

SOURCES = {
    "prelims": {
        "url": f"{RAU_BASE}/upsc-prelims/10-years-paper/",
        "out_dir": RAW_DIR / "prelims",
    },
    "mains": {
        "url": f"{RAU_BASE}/upsc-mains/10-years-paper/",
        "out_dir": RAW_DIR / "mains",
    },
}


def _is_pdf_link(href: str) -> bool:
    return bool(href and href.endswith(".pdf") and not href.startswith("#"))


def extract_pdf_links(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    current_year = None

    for el in soup.find_all(["h2", "h3", "h4", "a"]):
        tag = el.name
        if tag in ("h2", "h3", "h4"):
            ym = re.search(r"\b(20\d{2})\b", el.get_text())
            if ym:
                current_year = int(ym.group(1))
            continue

        href = el.get("href", "")
        if not _is_pdf_link(href):
            continue
        if href.startswith("/"):
            href = RAU_BASE + href
        text = el.get_text(strip=True)
        links.append({"url": href, "text": text, "year": current_year})

    return links


async def download_pdf(
    client: httpx.AsyncClient, url: str, dest: Path, sem: asyncio.Semaphore,
) -> bool:
    async with sem:
        try:
            resp = await client.get(url, timeout=60.0, follow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            logger.info("  Downloaded  %s  (%d KB)", dest.name, len(resp.content) // 1024)
            return True
        except Exception as e:
            logger.warning("  FAILED      %s: %s", url, e)
            return False


async def scrape_source(
    client: httpx.AsyncClient, key: str, source: dict, sem: asyncio.Semaphore,
) -> list[dict]:
    out_dir = source["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching %s page: %s", key, source["url"])
    resp = await client.get(source["url"], timeout=30.0)
    resp.raise_for_status()

    links = extract_pdf_links(resp.text, source["url"])
    logger.info("  Found %d PDF links for %s", len(links), key)

    tasks = []
    for link in links:
        # Build filename: year_paper-name.pdf
        year = link["year"] or "unknown"
        label = link["text"].replace("/", "_").replace(" ", "_").strip("_") or "paper"
        fname = f"{year}_{label}.pdf"
        # Clean duplicate underscores
        fname = re.sub(r"_+", "_", fname)
        dest = out_dir / fname
        if dest.exists():
            logger.info("  Skipped    %s (already exists)", fname)
            continue
        tasks.append(download_pdf(client, link["url"], dest, sem))

    if tasks:
        await asyncio.gather(*tasks)

    all_files = sorted(out_dir.glob("*.pdf"))
    logger.info("  %s: %d PDFs in %s", key, len(all_files), out_dir)
    return links


async def main(prelims: bool, mains: bool):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    sem = asyncio.Semaphore(3)

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TaaziKhabar/1.0)"},
    ) as client:
        if prelims:
            await scrape_source(client, "prelims", SOURCES["prelims"], sem)
        if mains:
            await scrape_source(client, "mains", SOURCES["mains"], sem)

    logger.info("Done.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prelims", action="store_true", help="Download Prelims papers")
    parser.add_argument("--mains", action="store_true", help="Download Mains papers")
    parser.add_argument("--all", action="store_true", help="Download all papers")
    args = parser.parse_args()

    if args.all or not (args.prelims or args.mains):
        args.prelims = args.mains = True

    asyncio.run(main(prelims=args.prelims, mains=args.mains))
