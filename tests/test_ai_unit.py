from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.ai.model_registry import ModelRegistry, ModelConfig
from app.ai.orchestrator import AIOrchestrator
from app.ai.personas.summarizer import build_prompt as summarizer_build_prompt, parse_response as summarizer_parse_response
from app.ai.personas.question_setter import build_prompt as qs_build_prompt, parse_response as qs_parse_response
from app.ai.training.collector import log_interaction
from app.ai.training.dataset_builder import build_dataset


SAMPLE_MODELS_YAML = """
models:
  summarizer:
    active: "meta/llama-3.1-8b-instruct"
    candidates:
      - name: "meta/llama-3.1-8b-instruct"
        provider: "nim"
        max_tokens: 1024
        temperature: 0.2
      - name: "mistralai/mistral-7b-instruct-v0.3"
        provider: "nim"
        max_tokens: 1024
        temperature: 0.2
  question_setter:
    active: "meta/llama-3.1-8b-instruct"
    candidates:
      - name: "meta/llama-3.1-8b-instruct"
        provider: "nim"
        max_tokens: 2048
        temperature: 0.4
"""


class TestModelRegistry:
    def test_load_and_get_active_model(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text(SAMPLE_MODELS_YAML)
        registry = ModelRegistry(config_path=config_file)
        model = registry.get_active_model("summarizer")
        assert isinstance(model, ModelConfig)
        assert model.name == "meta/llama-3.1-8b-instruct"
        assert model.provider == "nim"
        assert model.max_tokens == 1024
        assert model.temperature == 0.2

    def test_get_active_model_unknown_persona(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text(SAMPLE_MODELS_YAML)
        registry = ModelRegistry(config_path=config_file)
        assert registry.get_active_model("nonexistent") is None

    def test_list_models(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text(SAMPLE_MODELS_YAML)
        registry = ModelRegistry(config_path=config_file)
        models = registry.list_models()
        assert "summarizer" in models
        assert "question_setter" in models
        assert len(models["summarizer"]) == 2
        assert models["summarizer"][0]["active"] is True
        assert models["summarizer"][1]["active"] is False

    def test_set_active_model_raises_not_implemented(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text(SAMPLE_MODELS_YAML)
        registry = ModelRegistry(config_path=config_file)
        with pytest.raises(NotImplementedError):
            registry.set_active_model("summarizer", "some-model")

    def test_get_active_model_no_candidates_match(self, tmp_path):
        yaml_content = """
models:
  summarizer:
    active: "nonexistent-model"
    candidates:
      - name: "some-other-model"
        provider: "nim"
"""
        config_file = tmp_path / "models.yaml"
        config_file.write_text(yaml_content)
        registry = ModelRegistry(config_path=config_file)
        assert registry.get_active_model("summarizer") is None

    def test_empty_models(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text("models: {}\n")
        registry = ModelRegistry(config_path=config_file)
        assert registry.get_active_model("summarizer") is None
        assert registry.list_models() == {}


class TestSummarizerPersona:
    def test_build_prompt(self):
        system, prompt = summarizer_build_prompt("Test article body")
        assert "UPSC" in system
        assert "Test article body" in prompt
        assert "GK Gist" in prompt

    def test_build_prompt_empty_body(self):
        system, prompt = summarizer_build_prompt("")
        assert prompt

    def test_parse_response_full(self):
        response = """- GK Gist: Key point one.
- Key point two.
- Syllabus Topic: GS Paper 2 - Polity
- Key Terms: term1, term2, term3"""
        parsed = summarizer_parse_response(response)
        assert "Key point one" in parsed["gk_gist"]
        assert "GS Paper 2" in parsed["syllabus_topic"]
        assert parsed["key_terms"] == ["term1", "term2", "term3"]

    def test_parse_response_minimal(self):
        response = """GK Gist: Just one point.
Syllabus Topic: GS 3
Key Terms: term1"""
        parsed = summarizer_parse_response(response)
        assert parsed["gk_gist"]
        assert parsed["syllabus_topic"] == "GS 3"
        assert parsed["key_terms"] == ["term1"]

    def test_parse_response_no_key_terms(self):
        response = """- GK Gist: Point A
- Syllabus Topic: Topic X
- Key Terms:"""
        parsed = summarizer_parse_response(response)
        assert parsed["key_terms"] == []

    def test_parse_response_no_syllabus(self):
        response = """- GK Gist: Point A"""
        parsed = summarizer_parse_response(response)
        assert parsed["syllabus_topic"] == ""

    def test_parse_response_unformatted_fallback(self):
        response = "Raw text without any structure"
        parsed = summarizer_parse_response(response)
        assert parsed["gk_gist"] == response
        assert parsed["syllabus_topic"] == ""
        assert parsed["key_terms"] == []

    def test_parse_response_case_insensitive_headers(self):
        response = """gk gist: Lowercase point.
syllabus topic: GS 1
key terms: a, b"""
        parsed = summarizer_parse_response(response)
        assert "Lowercase" in parsed["gk_gist"]
        assert parsed["syllabus_topic"] == "GS 1"


class TestQuestionSetterPersona:
    def test_build_prompt(self):
        articles = [{"headline": "Test", "body_text": "Body content here. " * 20}]
        system, prompt = qs_build_prompt(articles, num_questions=5)
        assert "UPSC" in system
        assert "5" in prompt
        assert "Test" in prompt

    def test_build_prompt_multiple_articles(self):
        articles = [
            {"headline": "Article A", "body_text": "Content A. " * 20},
            {"headline": "Article B", "body_text": "Content B. " * 20},
        ]
        system, prompt = qs_build_prompt(articles, num_questions=3)
        assert "Article 1" in prompt
        assert "Article 2" in prompt

    def test_build_prompt_uses_gk_summary_when_available(self):
        articles = [{"headline": "Test", "gk_summary": "Short summary here", "body_text": "Long body ignored"}]
        system, prompt = qs_build_prompt(articles, num_questions=1)
        assert "Short summary here" in prompt

    def test_build_prompt_truncates_long_body(self):
        articles = [{"headline": "Test", "body_text": "X" * 5000}]
        system, prompt = qs_build_prompt(articles, num_questions=1)
        assert len(prompt) < 3000

    def test_parse_response_single_question(self):
        response = """Q: What is the capital of India?
A) Mumbai
B) New Delhi
C) Kolkata
D) Chennai
Answer: B
Explanation: New Delhi is the capital.
Difficulty: Easy"""
        questions = qs_parse_response(response)
        assert len(questions) == 1
        assert questions[0]["question_text"] == "What is the capital of India?"
        assert questions[0]["correct_answer"] == "B"
        assert questions[0]["options"]["A"] == "Mumbai"
        assert questions[0]["options"]["B"] == "New Delhi"
        assert questions[0]["difficulty"] == "Easy"

    def test_parse_response_multiple_questions(self):
        response = """Q: First question?
A) Opt A1
B) Opt B1
C) Opt C1
D) Opt D1
Answer: A
Explanation: Explanation 1.
Difficulty: Easy
---
Q: Second question?
A) Opt A2
B) Opt B2
C) Opt C2
D) Opt D2
Answer: C
Explanation: Explanation 2.
Difficulty: Hard"""
        questions = qs_parse_response(response)
        assert len(questions) == 2
        assert questions[1]["correct_answer"] == "C"
        assert questions[1]["difficulty"] == "Hard"

    def test_parse_response_question_without_answer_defaults_to_a(self):
        response = """Q: Just a question?
A) Opt A
B) Opt B
C) Opt C
D) Opt D"""
        questions = qs_parse_response(response)
        assert len(questions) == 1
        assert questions[0]["correct_answer"] == "A"

    def test_parse_response_empty_text(self):
        assert qs_parse_response("") == []
        assert qs_parse_response("   ") == []

    def test_parse_response_no_valid_blocks(self):
        response = "Some random text without any question format."
        assert qs_parse_response(response) == []

    def test_parse_response_partial_question(self):
        response = """Q: Partial question?
A) Only option A
Answer: A
Difficulty: Easy"""
        questions = qs_parse_response(response)
        assert len(questions) == 1
        assert questions[0]["options"]["A"] == "Only option A"
        assert "B" not in questions[0]["options"]


class TestLogInteraction:
    @pytest.mark.asyncio
    async def test_log_interaction_creates_record(self):
        db_mock = AsyncMock()
        interaction = await log_interaction(
            db=db_mock,
            persona="summarizer",
            model_used="test-model",
            prompt_text="Test prompt",
            response_text="Test response",
            tokens_used=100,
            latency_ms=500.0,
            user_id=uuid4(),
            article_id=uuid4(),
        )
        assert interaction.persona == "summarizer"
        assert interaction.model_used == "test-model"
        assert db_mock.add.called
        assert db_mock.flush.called

    @pytest.mark.asyncio
    async def test_log_interaction_minimal(self):
        db_mock = AsyncMock()
        interaction = await log_interaction(
            db=db_mock,
            persona="question_setter",
            model_used="test-model",
            prompt_text="Prompt",
            response_text="Response",
        )
        assert interaction.tokens_used is None
        assert interaction.latency_ms is None


class TestBuildDataset:
    @pytest.mark.asyncio
    async def test_build_dataset_returns_jsonl(self):
        db_mock = AsyncMock()
        mock_interaction = MagicMock()
        mock_interaction.prompt_text = "Summarize this"
        mock_interaction.response_text = "Here is a summary"
        mock_interaction.persona = "summarizer"
        mock_interaction.model_used = "test-model"

        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [mock_interaction]
        db_mock.execute.return_value = exec_result

        result = await build_dataset(db=db_mock, persona="summarizer")
        assert 'Summarize this' in result
        assert result.count("\n") == 0
        assert '"instruction":' in result
        assert '"output":' in result

    @pytest.mark.asyncio
    async def test_build_dataset_empty(self):
        db_mock = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = exec_result

        result = await build_dataset(db=db_mock, persona="summarizer")
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_dataset_filters_by_persona(self):
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock()
        exec_result = AsyncMock()
        exec_result.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = exec_result

        await build_dataset(db=db_mock, persona="question_setter")
        call_args = db_mock.execute.call_args[0][0]
        compiled = str(call_args)
        assert "question_setter" in compiled


class TestAIOrchestrator:
    @pytest.mark.asyncio
    async def test_summarize_article_no_model_raises(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text("models: {}\n")
        with patch("app.ai.orchestrator.registry", ModelRegistry(config_path=config_file)):
            orchestrator = AIOrchestrator()
            with pytest.raises(ValueError, match="No active model"):
                await orchestrator.summarize_article("Some article body")

    @pytest.mark.asyncio
    async def test_generate_mcq_no_model_raises(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text("models: {}\n")
        with patch("app.ai.orchestrator.registry", ModelRegistry(config_path=config_file)):
            orchestrator = AIOrchestrator()
            with pytest.raises(ValueError, match="No active model"):
                await orchestrator.generate_mcq(articles=[{"headline": "Test", "body_text": "Body"}])
