"""Seed script to populate exam_questions table with sample UPSC questions."""
import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.exam_question import ExamQuestion

SAMPLE_QUESTIONS = [
    {
        "source_exam": "UPSC Prelims",
        "year": "2024",
        "subject": "Polity",
        "question_text": "Which of the following articles of the Constitution of India deals with the Fundamental Duties?",
        "options": {
            "A": "Article 51A",
            "B": "Article 32",
            "C": "Article 14",
            "D": "Article 21",
        },
        "correct_answer": "A",
        "explanation": "Article 51A of the Constitution of India deals with Fundamental Duties, added by the 42nd Amendment Act, 1976.",
        "topic": "Fundamental Duties",
    },
    {
        "source_exam": "UPSC Prelims",
        "year": "2024",
        "subject": "Economy",
        "question_text": "Consider the following statements regarding the Goods and Services Tax (GST) Council:",
        "options": {
            "A": "It is a constitutional body",
            "B": "It is chaired by the Prime Minister",
            "C": "It decides the tax rates for GST",
            "D": "Both A and C",
        },
        "correct_answer": "D",
        "explanation": "The GST Council is a constitutional body under Article 279A, chaired by the Union Finance Minister, and recommends GST tax rates.",
        "topic": "GST",
    },
    {
        "source_exam": "UPSC Prelims",
        "year": "2023",
        "subject": "Environment",
        "question_text": "Which of the following is a 'Ramsar site' in India?",
        "options": {
            "A": "Chilika Lake",
            "B": "Dal Lake",
            "C": "Loktak Lake",
            "D": "All of the above",
        },
        "correct_answer": "D",
        "explanation": "Chilika Lake (Odisha), Dal Lake (Jammu & Kashmir), and Loktak Lake (Manipur) are all designated Ramsar sites in India.",
        "topic": "Ramsar Sites",
    },
    {
        "source_exam": "UPSC Prelims",
        "year": "2023",
        "subject": "History",
        "question_text": "The 'Drain of Wealth' theory was propounded by:",
        "options": {
            "A": "Dadabhai Naoroji",
            "B": "Mahatma Gandhi",
            "C": "Jawaharlal Nehru",
            "D": "B.R. Ambedkar",
        },
        "correct_answer": "A",
        "explanation": "Dadabhai Naoroji propounded the 'Drain of Wealth' theory in his book 'Poverty and Un-British Rule in India'.",
        "topic": "Economic History",
    },
    {
        "source_exam": "UPSC Prelims",
        "year": "2022",
        "subject": "Geography",
        "question_text": "Which of the following rivers flows through a rift valley?",
        "options": {
            "A": "Narmada",
            "B": "Godavari",
            "C": "Krishna",
            "D": "Mahanadi",
        },
        "correct_answer": "A",
        "explanation": "The Narmada river flows through a rift valley between the Vindhya and Satpura mountain ranges.",
        "topic": "Indian Rivers",
    },
]


async def seed() -> None:
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for q_data in SAMPLE_QUESTIONS:
            question = ExamQuestion(**q_data)
            session.add(question)
        await session.commit()
        print(f"Seeded {len(SAMPLE_QUESTIONS)} exam questions")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
