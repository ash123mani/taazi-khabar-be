import io
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_admin_user
from app.models.user import User
from app.models.article import Article
from app.models.category import Category
from app.models.ai_interaction import AIInteraction
from app.ai.model_registry import registry
from app.services import training_service

router = APIRouter()


@router.get("/scrape-dates", response_model=dict)
async def list_scrape_dates(
    days: int = Query(30, ge=1, le=90),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Article.source, cast(Article.published_at, Date).label("d"))
        .distinct()
        .order_by(Article.source, cast(Article.published_at, Date).desc())
    )
    scraped: dict[str, set[str]] = {}
    for row in result:
        scraped.setdefault(row.source, set()).add(row.d.isoformat())

    today = date.today()
    date_range = [(today - timedelta(days=i)).isoformat() for i in range(days)]

    sources = ["thehindu", "indianexpress"]
    dates_dto = {}
    for source in sources:
        dates_dto[source] = [
            {"date": d, "scraped": d in scraped.get(source, set())}
            for d in date_range
        ]

    return {"dates": dates_dto}


@router.get("/scrape-summary", response_model=dict)
async def scrape_summary(
    days: int = Query(30, ge=1, le=90),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    since = date.today() - timedelta(days=days)
    rows = await db.execute(
        select(
            Article.source,
            cast(Article.published_at, Date).label("pub_date"),
            func.count(Article.id).label("total"),
            func.array_agg(func.distinct(func.date_trunc("minute", Article.scraped_at))).label("scrape_times"),
            Article.syllabus_tag,
        )
        .where(cast(Article.published_at, Date) >= since)
        .group_by(Article.source, cast(Article.published_at, Date), Article.syllabus_tag)
        .order_by(Article.source, cast(Article.published_at, Date).desc())
    )
    rows_all = rows.all()

    sources: dict[str, dict] = {}
    for source, pub_date, total, scrape_times, syllabus_tag in rows_all:
        ds = pub_date.isoformat()
        src = sources.setdefault(source, {})
        day = src.setdefault(ds, {"date": ds, "total_articles": 0, "scrape_times": set(), "categories": {}})
        day["total_articles"] += total
        if scrape_times:
            for t in scrape_times:
                if t:
                    day["scrape_times"].add(t.isoformat())
        if syllabus_tag:
            cat = syllabus_tag.split(":")[0].strip() if ":" in syllabus_tag else syllabus_tag
            day["categories"][cat] = day["categories"].get(cat, 0) + total

    all_sources = set(sources.keys()) | {"thehindu", "indianexpress"}
    today = date.today()
    date_range = [(today - timedelta(days=i)).isoformat() for i in range(days)]

    result = {}
    for source in sorted(all_sources):
        days_data = sources.get(source, {})
        result[source] = []
        for d in reversed(date_range):
            if d in days_data:
                day = days_data[d]
                day["scrape_times"] = sorted(day["scrape_times"])
                result[source].append(day)
            else:
                result[source].append({
                    "date": d,
                    "total_articles": 0,
                    "scrape_times": [],
                    "categories": {},
                })

    return {"sources": result}


@router.post("/scrape-date", response_model=dict)
async def scrape_date(
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    source = data.get("source")
    target_date = data.get("date")

    if source not in ("thehindu", "indianexpress"):
        raise HTTPException(status_code=400, detail="source must be thehindu or indianexpress")
    if not target_date:
        raise HTTPException(status_code=400, detail="date is required (YYYY-MM-DD)")

    from app.scrapers.the_hindu import TheHinduScraper
    from app.scrapers.indian_express import IndianExpressScraper
    from app.services.article_service import bulk_upsert_articles
    from app.ai.orchestrator import AIOrchestrator

    scraper = TheHinduScraper() if source == "thehindu" else IndianExpressScraper()

    try:
        articles = await scraper.scrape()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Scrape failed: {e}")

    filtered = [a for a in articles if a.published_at[:10] == target_date]

    orchestrator = AIOrchestrator()

    async def summarize(body: str, article_id=None, db=None):
        return await orchestrator.summarize_article(article_body=body, article_id=article_id, db=db)

    async def filterer(headline: str, body_text: str):
        return await orchestrator.filter_article(headline=headline, body_text=body_text, db=db)

    async def question_setter(article_id, headline, summary, syllabus_tag, key_terms):
        return await orchestrator.generate_mcq_for_article(
            article={
                "id": str(article_id),
                "headline": headline,
                "gk_summary": summary,
                "syllabus_tag": syllabus_tag or "",
                "key_terms": key_terms or [],
            },
            num_questions=3,
        )

    created, skipped, summary_errors, filtered_out = await bulk_upsert_articles(
        db=db,
        articles=filtered,
        summarizer=summarize,
        article_filter=filterer,
        question_setter=question_setter,
    )

    return {
        "source": source,
        "date": target_date,
        "articles_found": len(filtered),
        "articles_created": created,
        "articles_skipped": skipped,
        "articles_filtered_out": filtered_out,
        "errors": summary_errors,
    }


@router.get("/scrape-articles", response_model=dict)
async def scrape_articles(
    source: str = Query(...),
    date_str: str = Query(alias="date"),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    result = await db.execute(
        select(Article)
        .where(
            Article.source == source,
            cast(Article.published_at, Date) == parsed,
        )
        .order_by(Article.published_at.desc())
    )
    articles = result.scalars().all()
    return {
        "articles": [
            {
                "id": str(a.id),
                "source": a.source,
                "headline": a.headline,
                "url": a.url,
                "published_at": a.published_at.isoformat(),
                "gk_summary": a.gk_summary,
                "key_terms": a.key_terms,
                "syllabus_tag": a.syllabus_tag,
                "image_url": a.image_url,
                "scraped_at": a.scraped_at.isoformat() if a.scraped_at else None,
            }
            for a in articles
        ]
    }


@router.get("/articles", response_model=dict)
async def admin_list_articles(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    source: str | None = Query(None),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import article_service
    
    query = select(Article).order_by(Article.published_at.desc())
    count_query = select(func.count()).select_from(Article)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Article.headline.ilike(search_term)) |
            (Article.url.ilike(search_term))
        )
        count_query = count_query.where(
            (Article.headline.ilike(search_term)) |
            (Article.url.ilike(search_term))
        )
    
    if source:
        query = query.where(Article.source == source)
        count_query = count_query.where(Article.source == source)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    result = await db.execute(query.offset(skip).limit(limit))
    articles = result.scalars().all()
    
    return {
        "total": total,
        "articles": [
            {
                "id": str(a.id),
                "source": a.source,
                "headline": a.headline,
                "url": a.url,
                "published_at": a.published_at.isoformat(),
                "gk_summary": a.gk_summary,
                "key_terms": a.key_terms,
                "syllabus_tag": a.syllabus_tag,
                "image_url": a.image_url,
                "scraped_at": a.scraped_at.isoformat() if a.scraped_at else None,
            }
            for a in articles
        ],
    }


@router.delete("/articles/{article_id}", response_model=dict)
async def admin_delete_article(
    article_id: UUID,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    await db.delete(article)
    await db.commit()
    
    return {"status": "deleted", "id": str(article_id)}


@router.get("/categories", response_model=dict)
async def admin_list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).order_by(Category.name.asc())
    count_query = select(func.count()).select_from(Category)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(Category.name.ilike(search_term))
        count_query = count_query.where(Category.name.ilike(search_term))
    
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    result = await db.execute(query.offset(skip).limit(limit))
    categories = result.scalars().all()
    
    return {
        "total": total,
        "categories": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "created_at": c.created_at.isoformat(),
            }
            for c in categories
        ],
    }


@router.post("/categories", response_model=dict)
async def admin_create_category(
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    name = data.get("name")
    description = data.get("description")
    
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    
    # Check if name already exists
    result = await db.execute(select(Category).where(Category.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Category with this name already exists")
    
    category = Category(name=name, description=description)
    db.add(category)
    await db.flush()
    await db.commit()
    
    return {
        "status": "created",
        "id": str(category.id),
        "name": category.name,
        "description": category.description,
    }


@router.put("/categories/{category_id}", response_model=dict)
async def admin_update_category(
    category_id: UUID,
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    name = data.get("name")
    description = data.get("description")
    
    if name is not None:
        # Check if another category has this name
        if name != category.name:
            result = await db.execute(
                select(Category).where(Category.name == name, Category.id != category_id)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Category with this name already exists")
        category.name = name
    
    if description is not None:
        category.description = description
    
    await db.flush()
    await db.commit()
    
    return {
        "status": "updated",
        "id": str(category.id),
        "name": category.name,
        "description": category.description,
    }


@router.delete("/categories/{category_id}", response_model=dict)
async def admin_delete_category(
    category_id: UUID,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # TODO: Consider what to do with articles that reference this category
    # For now, we'll allow deletion and set category_id to NULL in articles? 
    # But the Article model has category_id as nullable, so we can set it to NULL.
    # However, we don't want to cascade delete articles.
    # We'll set category_id to NULL for articles that reference this category.
    from sqlalchemy import update
    await db.execute(
        update(Article)
        .where(Article.category_id == category_id)
        .values(category_id=None)
    )
    
    await db.delete(category)
    await db.commit()
    
    return {"status": "deleted", "id": str(category_id)}


@router.get("/users", response_model=dict)
async def admin_list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())
    count_query = select(func.count()).select_from(User)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (User.email.ilike(search_term)) |
            (User.name.ilike(search_term))
        )
        count_query = count_query.where(
            (User.email.ilike(search_term)) |
            (User.name.ilike(search_term))
        )
    
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    result = await db.execute(query.offset(skip).limit(limit))
    users = result.scalars().all()
    
    return {
        "total": total,
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
    }


@router.put("/users/{user_id}/role", response_model=dict)
async def admin_update_user_role(
    user_id: UUID,
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    is_admin = data.get("is_admin")
    if is_admin is None:
        raise HTTPException(status_code=400, detail="is_admin is required")
    
    user.is_admin = is_admin
    
    await db.flush()
    await db.commit()
    
    return {
        "status": "updated",
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "is_admin": user.is_admin,
    }


@router.get("/articles-without-summary", response_model=dict)
async def list_articles_without_summary(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Article)
        .where(Article.gk_summary.is_(None))
        .order_by(Article.published_at.desc())
        .offset(skip)
        .limit(limit)
    )
    articles = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(Article).where(Article.gk_summary.is_(None))
    )
    total = count_result.scalar()

    return {
        "total": total,
        "articles": [
            {
                "id": str(a.id),
                "source": a.source,
                "headline": a.headline,
                "url": a.url,
                "published_at": a.published_at.isoformat(),
            }
            for a in articles
        ],
    }


@router.post("/generate-summaries", response_model=dict)
async def generate_summaries(
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    article_ids = data.get("article_ids", [])
    if not article_ids:
        raise HTTPException(status_code=400, detail="article_ids is required")

    from app.ai.orchestrator import AIOrchestrator

    uuids = [UUID(id) for id in article_ids]
    result = await db.execute(select(Article).where(Article.id.in_(uuids)))
    articles = result.scalars().all()

    from app.models.cached_question import CachedQuestion

    orchestrator = AIOrchestrator()
    updated = 0
    errors = []

    async def process_article(article):
        nonlocal updated
        try:
            summary = await orchestrator.summarize_article(
                article_body=article.body_text,
                article_id=article.id,
                db=db,
            )
            article.gk_summary = summary.get("gk_gist")
            article.syllabus_tag = summary.get("syllabus_topic")
            article.key_terms = summary.get("key_terms")

            # Generate and cache questions
            try:
                questions = await orchestrator.generate_mcq_for_article(
                    article={
                        "id": str(article.id),
                        "headline": article.headline,
                        "gk_summary": article.gk_summary or "",
                        "syllabus_tag": article.syllabus_tag or "",
                        "key_terms": article.key_terms or [],
                    },
                    num_questions=3,
                )
                existing = await db.execute(
                    select(CachedQuestion.id)
                    .where(CachedQuestion.article_id == article.id)
                    .limit(1)
                )
                if existing.scalar_one_or_none() is None:
                    for q in questions:
                        db.add(CachedQuestion(
                            article_id=article.id,
                            question_text=q["question_text"],
                            options=q["options"],
                            correct_answer=q["correct_answer"],
                            explanation=q.get("explanation"),
                            difficulty=q.get("difficulty"),
                        ))
            except Exception as qe:
                errors.append(f"Questions failed for {article.id}: {qe}")

            updated += 1
        except Exception as e:
            errors.append(f"{article.id}: {e}")

    for article in articles:
        await process_article(article)

    await db.commit()

    return {"updated": updated, "errors": errors}


@router.get("/interactions", response_model=list[dict])
async def list_interactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    persona: str | None = Query(None),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    interactions = await training_service.list_interactions(
        db=db, skip=skip, limit=limit, persona=persona
    )
    return [
        {
            "id": str(i.id),
            "persona": i.persona,
            "model_used": i.model_used,
            "prompt": i.prompt_text,
            "response": i.response_text,
            "tokens_used": i.tokens_used,
            "latency_ms": i.latency_ms,
            "user_feedback": i.user_feedback,
            "user_id": str(i.user_id) if i.user_id else None,
            "created_at": i.created_at.isoformat(),
        }
        for i in interactions
    ]


@router.put("/interactions/{interaction_id}", response_model=dict)
async def update_interaction(
    interaction_id: UUID,
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIInteraction).where(AIInteraction.id == interaction_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        raise HTTPException(status_code=404, detail="Interaction not found")

    for key, value in data.items():
        if hasattr(interaction, key):
            setattr(interaction, key, value)

    await db.flush()
    await db.refresh(interaction)
    return {"status": "updated", "id": str(interaction_id)}


@router.get("/datasets", response_model=dict)
async def list_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    datasets = await training_service.list_datasets(db=db, skip=skip, limit=limit)
    return {
        "datasets": [
            {
                "id": str(d.id),
                "name": d.persona,
                "persona": d.persona,
                "num_examples": d.record_count,
                "status": "ready",
                "lora_adapter_path": None,
                "created_at": d.created_at.isoformat(),
            }
            for d in datasets
        ]
    }


@router.post("/datasets", response_model=dict)
async def create_dataset(
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    persona = data.get("persona")
    if not persona:
        raise HTTPException(status_code=400, detail="persona is required")

    from app.ai.training.dataset_builder import build_dataset

    dataset_jsonl = await build_dataset(db=db, persona=persona)
    record_count = len([l for l in dataset_jsonl.split("\n") if l.strip()])

    dataset = await training_service.save_dataset(
        db=db,
        persona=persona,
        dataset_jsonl=dataset_jsonl,
        record_count=record_count,
    )

    return {
        "status": "created",
        "id": str(dataset.id),
        "persona": dataset.persona,
        "num_examples": dataset.record_count,
    }


@router.get("/datasets/{dataset_id}/download")
async def download_dataset(
    dataset_id: UUID,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await training_service.get_dataset_by_id(db=db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    stream = io.StringIO(dataset.dataset_jsonl)
    filename = f"{dataset.persona}-dataset-{dataset.created_at.strftime('%Y%m%d')}.jsonl"
    return StreamingResponse(
        iter([stream.read()]),
        media_type="application/jsonl",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/models", response_model=dict)
async def list_models(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    models = await registry.db_list_models(db=db)
    grouped: dict[str, list[dict]] = {}
    for m in models:
        persona = m["persona"]
        grouped.setdefault(persona, []).append({
            "id": m["id"],
            "name": m["model_name"],
            "provider": m["provider"],
            "active": m["is_active"],
        })
    return grouped


@router.put("/models", response_model=dict)
async def update_model(
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    persona = data.get("persona")
    model_name = data.get("model_name") or data.get("active_model_id")

    if not persona or not model_name:
        raise HTTPException(status_code=400, detail="persona and model_name (or active_model_id) required")

    success = await registry.db_set_active_model(db=db, persona=persona, model_name=model_name)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found for persona")
    return {"status": "updated", "persona": persona, "active_model": model_name}
