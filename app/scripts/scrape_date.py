"""
Usage: python -m app.scripts.scrape_date 2026-06-06

Scrapes both The Hindu and Indian Express for the given date,
runs AI summarization and relevance filtering for each article.
"""

import asyncio
import sys
from datetime import date

import httpx

from app.config import settings

API_BASE = "http://localhost:8000/api"
SOURCES = ["thehindu", "indianexpress"]


async def login() -> str:
    async with httpx.AsyncClient(base_url=API_BASE) as client:
        r = await client.post(
            "/auth/login",
            json={
                "email": settings.admin_email,
                "password": settings.admin_password.get_secret_value(),
            },
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def scrape_date(token: str, target_date: str, source: str) -> dict:
    async with httpx.AsyncClient(base_url=API_BASE) as client:
        r = await client.post(
            "/admin/scrape-date",
            headers={"Authorization": f"Bearer {token}"},
            json={"source": source, "date": target_date},
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()


async def main():
    if len(sys.argv) < 2:
        print(f"Usage: python -m app.scripts.scrape_date YYYY-MM-DD")
        sys.exit(1)

    target_date = sys.argv[1]

    try:
        date.fromisoformat(target_date)
    except ValueError:
        print(f"Invalid date format: {target_date}. Use YYYY-MM-DD.")
        sys.exit(1)

    print(f"Logging in as {settings.admin_email}...")
    token = await login()
    print("Login OK\n")

    for source in SOURCES:
        print(f"{'='*60}")
        print(f"Scraping {source} for {target_date}...")
        print(f"{'='*60}")
        try:
            result = await scrape_date(token, target_date, source)
            print(f"  Articles found:      {result['articles_found']}")
            print(f"  Articles created:    {result['articles_created']}")
            print(f"  Articles skipped:    {result['articles_skipped']}")
            print(f"  Filtered out:        {result['articles_filtered_out']}")
            errors = result.get("errors", [])
            if errors:
                print(f"  Errors ({len(errors)}):")
                for err in errors[:5]:
                    print(f"    - {err}")
                if len(errors) > 5:
                    print(f"    ... and {len(errors) - 5} more")
        except Exception as e:
            print(f"  FAILED: {e}")
        print()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
