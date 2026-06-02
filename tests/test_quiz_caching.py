"""Tests for quiz caching logic in quiz_service."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.quiz_service import compute_article_set_hash, find_existing_quiz, create_quiz


class TestComputeArticleSetHash:
    def test_same_ids_same_hash(self):
        id_a = uuid4()
        id_b = uuid4()
        hash1 = compute_article_set_hash([id_a, id_b], 5)
        hash2 = compute_article_set_hash([id_b, id_a], 5)
        assert hash1 == hash2

    def test_different_ids_different_hash(self):
        id_a = uuid4()
        id_b = uuid4()
        hash1 = compute_article_set_hash([id_a], 5)
        hash2 = compute_article_set_hash([id_b], 5)
        assert hash1 != hash2

    def test_different_num_questions_different_hash(self):
        id_a = uuid4()
        hash1 = compute_article_set_hash([id_a], 5)
        hash2 = compute_article_set_hash([id_a], 10)
        assert hash1 != hash2

    def test_deterministic_output(self):
        ids = [uuid4() for _ in range(3)]
        hash1 = compute_article_set_hash(ids, 5)
        hash2 = compute_article_set_hash(ids, 5)
        assert hash1 == hash2

    def test_md5_format(self):
        ids = [uuid4()]
        result = compute_article_set_hash(ids, 5)
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)


class TestFindExistingQuiz:
    @pytest.mark.asyncio
    async def test_no_existing_quiz_returns_none(self, mocker):
        db_mock = mocker.AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        db_mock.execute.return_value = exec_result
        result = await find_existing_quiz(db_mock, "abcdef1234567890abcdef1234567890")
        assert result is None

    @pytest.mark.asyncio
    async def test_existing_quiz_returns_quiz(self, mocker):
        mock_quiz = mocker.MagicMock()
        mock_quiz.id = uuid4()
        mock_quiz.article_set_hash = "abcdef1234567890abcdef1234567890"

        db_mock = mocker.AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_quiz
        db_mock.execute.return_value = exec_result

        result = await find_existing_quiz(db_mock, "abcdef1234567890abcdef1234567890")
        assert result is mock_quiz


class TestCreateQuiz:
    @pytest.mark.asyncio
    async def test_creates_quiz_with_questions(self, mocker):
        db_mock = mocker.AsyncMock()
        user_id = uuid4()
        article_set_hash = "testhash123"
        article = mocker.MagicMock()
        article.id = uuid4()

        questions_data = [
            {
                "question_text": "Test Q?",
                "options": {"A": "Opt1", "B": "Opt2", "C": "Opt3", "D": "Opt4"},
                "correct_answer": "A",
                "explanation": "Exp",
                "difficulty": "Easy",
            }
        ]

        quiz = await create_quiz(
            db=db_mock,
            user_id=user_id,
            article_set_hash=article_set_hash,
            articles=[article],
            questions_data=questions_data,
            title="Test Quiz",
        )

        assert quiz.user_id == user_id
        assert quiz.article_set_hash == article_set_hash
        assert quiz.title == "Test Quiz"
        assert quiz.total_questions == 1
        assert db_mock.add.call_count >= 2
        assert db_mock.flush.call_count >= 1
