from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_admin_user
from app.models.user import User
from app.scrapers.the_hindu import TheHinduScraper
from app.scrapers.indian_express import IndianExpressScraper
from app.services.article_service import bulk_upsert_articles
from app.ai.orchestrator import AIOrchestrator

router = APIRouter()


@router.post("/scrape")
async def scrape_articles(
    source: str = Query("all", pattern="^(all|the_hindu|indian_express)$"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    scrapers = []
    if source in ("all", "the_hindu"):
        scrapers.append(TheHinduScraper())
    if source in ("all", "indian_express"):
        scrapers.append(IndianExpressScraper())

    all_articles = []
    scrape_errors = []

    for scraper in scrapers:
        try:
            articles = await scraper.scrape()
            all_articles.extend(articles)
        except Exception as e:
            scrape_errors.append(f"{scraper.__class__.__name__}: {e}")

    orchestrator = AIOrchestrator()

    async def summarize(body: str, article_id=None, db=None):
        return await orchestrator.summarize_article(
            article_body=body,
            article_id=article_id,
            db=db,
        )

    async def filterer(headline: str, body_text: str):
        return await orchestrator.filter_article(
            headline=headline,
            body_text=body_text,
            db=db,
        )

    created, skipped, summary_errors, filtered_out = await bulk_upsert_articles(
        db=db,
        articles=all_articles,
        summarizer=summarize,
        article_filter=filterer,
    )

    all_errors = scrape_errors + summary_errors

    return {
        "articles_created": created,
        "articles_skipped": skipped,
        "articles_filtered_out": filtered_out,
        "errors": all_errors,
    }
