from __future__ import annotations

from uuid import uuid4
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header
from app.models.article import Article
from app.models.category import Category


async def seed_articles(db: AsyncSession, count: int = 5, source: str = "the_hindu") -> list[Article]:
    articles = []
    for i in range(count):
        article = Article(
            source=source,
            headline=f"Test Article {i + 1}",
            body_text=f"Body of article {i + 1}." * 20,
            url=f"https://example.com/article-{source}-{i + 1}",
            published_at=datetime(2026, 6, i + 1, tzinfo=timezone.utc),
            gk_summary=f"Summary {i + 1}" if i % 2 == 0 else None,
            key_terms=[f"term{i + 1}a", f"term{i + 1}b"] if i % 2 == 0 else None,
            syllabus_tag=f"Topic {i + 1}" if i % 2 == 0 else None,
        )
        db.add(article)
        articles.append(article)
    await db.flush()
    for a in articles:
        await db.refresh(a)
    return articles


class TestListArticles:
    async def test_list_empty(self, client: AsyncClient, db_session: AsyncSession):
        res = await client.get("/api/articles")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["articles"] == []

    async def test_list_with_data(self, client: AsyncClient, db_session: AsyncSession):
        await seed_articles(db_session, count=3)
        res = await client.get("/api/articles")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 3
        assert len(data["articles"]) == 3

    async def test_list_filter_by_source(self, client: AsyncClient, db_session: AsyncSession):
        await seed_articles(db_session, count=3, source="the_hindu")
        await seed_articles(db_session, count=2, source="indian_express")
        res = await client.get("/api/articles?source=the_hindu")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 3
        assert all(a["source"] == "the_hindu" for a in data["articles"])

    async def test_list_filter_by_source_no_results(self, client: AsyncClient, db_session: AsyncSession):
        await seed_articles(db_session, count=2, source="the_hindu")
        res = await client.get("/api/articles?source=indian_express")
        assert res.status_code == 200
        assert res.json()["total"] == 0

    async def test_list_pagination(self, client: AsyncClient, db_session: AsyncSession):
        await seed_articles(db_session, count=10)
        res = await client.get("/api/articles?skip=0&limit=3")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 10
        assert len(data["articles"]) == 3

    async def test_list_pagination_offset(self, client: AsyncClient, db_session: AsyncSession):
        await seed_articles(db_session, count=5)
        res = await client.get("/api/articles?skip=3&limit=10")
        assert res.status_code == 200
        assert len(res.json()["articles"]) == 2

    async def test_list_invalid_limit(self, client: AsyncClient):
        res = await client.get("/api/articles?limit=101")
        assert res.status_code == 422

    async def test_list_invalid_skip(self, client: AsyncClient):
        res = await client.get("/api/articles?skip=-1")
        assert res.status_code == 422

    async def test_list_filter_by_category(self, client: AsyncClient, db_session: AsyncSession):
        cat = Category(name="Polity", description="Polity articles")
        db_session.add(cat)
        await db_session.flush()
        await db_session.refresh(cat)
        articles = await seed_articles(db_session, count=3)
        for a in articles:
            a.category_id = cat.id
        await db_session.flush()
        res = await client.get(f"/api/articles?category_id={cat.id}")
        assert res.status_code == 200
        assert res.json()["total"] == 3


class TestGetArticle:
    async def test_get_by_id_success(self, client: AsyncClient, db_session: AsyncSession):
        articles = await seed_articles(db_session, count=1)
        article_id = articles[0].id
        res = await client.get(f"/api/articles/{article_id}")
        assert res.status_code == 200
        assert res.json()["headline"] == "Test Article 1"

    async def test_get_by_id_not_found(self, client: AsyncClient):
        res = await client.get(f"/api/articles/{uuid4()}")
        assert res.status_code == 404

    async def test_get_by_id_invalid_uuid(self, client: AsyncClient):
        res = await client.get("/api/articles/not-a-uuid")
        assert res.status_code == 422

    async def test_get_by_id_returns_all_fields(self, client: AsyncClient, db_session: AsyncSession):
        articles = await seed_articles(db_session, count=1)
        a = articles[0]
        res = await client.get(f"/api/articles/{a.id}")
        data = res.json()
        assert data["source"] == a.source
        assert data["headline"] == a.headline
        assert data["body_text"] == a.body_text
        assert data["url"] == a.url
        assert "published_at" in data
        assert "scraped_at" in data
        assert data["gk_summary"] == a.gk_summary
        assert data["syllabus_tag"] == a.syllabus_tag
