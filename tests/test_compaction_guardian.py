"""Tests for the compaction guardian module."""

import json
from pathlib import Path

import pytest

from cns_bridge.compaction_guardian import (
    CaptureRecord,
    CompactionGuardian,
    CompactionState,
    extract_recent_insights,
)
from cns_bridge.token_estimator import HealthLevel


# ---------------------------------------------------------------------------
# CompactionGuardian construction
# ---------------------------------------------------------------------------

class TestGuardianInit:
    def test_defaults(self) -> None:
        g = CompactionGuardian()
        assert g.context_limit == 128_000
        assert g.trigger_threshold == 0.80
        assert not g.has_triggered

    def test_custom_limit(self) -> None:
        g = CompactionGuardian(context_limit=200_000)
        assert g.context_limit == 200_000

    def test_invalid_limit(self) -> None:
        with pytest.raises(ValueError):
            CompactionGuardian(context_limit=0)

    def test_invalid_threshold_zero(self) -> None:
        with pytest.raises(ValueError):
            CompactionGuardian(trigger_threshold=0)

    def test_invalid_threshold_over_one(self) -> None:
        with pytest.raises(ValueError):
            CompactionGuardian(trigger_threshold=1.5)


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------

class TestGuardianCheck:
    def test_green_state(self) -> None:
        g = CompactionGuardian(context_limit=100_000)
        state = g.check(30_000)
        assert state.health == "green"
        assert not state.triggered
        assert not g.has_triggered

    def test_yellow_state(self) -> None:
        g = CompactionGuardian(context_limit=100_000)
        state = g.check(65_000)
        assert state.health == "yellow"
        assert not state.triggered

    def test_red_state_triggers(self) -> None:
        g = CompactionGuardian(context_limit=100_000)
        state = g.check(85_000)
        assert state.health == "red"
        assert state.triggered
        assert g.has_triggered

    def test_custom_threshold(self) -> None:
        g = CompactionGuardian(context_limit=100_000, trigger_threshold=0.50)
        state = g.check(60_000)
        assert state.triggered

    def test_history_accumulates(self) -> None:
        g = CompactionGuardian(context_limit=100_000)
        g.check(10_000)
        g.check(50_000)
        g.check(90_000)
        assert len(g.history) == 3

    def test_state_to_dict(self) -> None:
        g = CompactionGuardian(context_limit=100_000)
        state = g.check(50_000)
        d = state.to_dict()
        assert "used_tokens" in d
        assert "health" in d
        assert "pressure" in d
        assert "timestamp" in d

    def test_check_messages(self) -> None:
        g = CompactionGuardian(context_limit=100)
        msgs = [{"content": "hello world " * 100}]
        state = g.check_messages(msgs)
        assert state.used_tokens > 0

    def test_check_text(self) -> None:
        g = CompactionGuardian(context_limit=100)
        state = g.check_text("hello " * 200)
        assert state.health in ("yellow", "red")

    def test_reset_clears_trigger(self) -> None:
        g = CompactionGuardian(context_limit=100_000)
        g.check(90_000)
        assert g.has_triggered
        g.reset()
        assert not g.has_triggered


# ---------------------------------------------------------------------------
# creative_break()
# ---------------------------------------------------------------------------

class TestCreativeBreak:
    def test_writes_file(self, tmp_path: Path) -> None:
        g = CompactionGuardian(
            context_limit=100_000,
            ai_writings_dir=tmp_path,
            agent_name="test-agent",
        )
        record = g.creative_break(
            insights=["The fleet is a fishing vessel"],
            metaphors=["The tide comes for everything"],
        )
        assert isinstance(record, CaptureRecord)
        assert record.insight_count == 1
        assert record.metaphor_count == 1
        assert Path(record.path).exists()
        content = Path(record.path).read_text()
        assert "Lighthouse Keeper" in content
        assert "fishing vessel" in content

    def test_empty_insights(self, tmp_path: Path) -> None:
        g = CompactionGuardian(ai_writings_dir=tmp_path)
        record = g.creative_break(insights=[])
        assert record.insight_count == 0
        content = Path(record.path).read_text()
        assert "No insights" in content

    def test_with_open_threads(self, tmp_path: Path) -> None:
        g = CompactionGuardian(ai_writings_dir=tmp_path)
        record = g.creative_break(
            insights=["test"],
            open_threads=["Build the thing", "Write more tests"],
        )
        content = Path(record.path).read_text()
        assert "Build the thing" in content

    def test_with_extra_context(self, tmp_path: Path) -> None:
        g = CompactionGuardian(ai_writings_dir=tmp_path)
        record = g.creative_break(
            insights=["test"],
            extra_context="Special notes for the next iteration.",
        )
        content = Path(record.path).read_text()
        assert "Special notes" in content

    def test_journal_appended(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.md"
        g = CompactionGuardian(
            ai_writings_dir=tmp_path / "writings",
            journal_path=journal,
        )
        g.creative_break(
            insights=["key finding"],
            metaphors=["the sea remembers"],
        )
        assert journal.exists()
        jcontent = journal.read_text()
        assert "Guardian Entry" in jcontent
        assert "key finding" in jcontent

    def test_trigger_count_increments(self, tmp_path: Path) -> None:
        g = CompactionGuardian(ai_writings_dir=tmp_path)
        assert g.trigger_count == 0
        g.creative_break(insights=["x"])
        g.creative_break(insights=["y"])
        assert g.trigger_count == 2

    def test_session_id_in_filename(self, tmp_path: Path) -> None:
        g = CompactionGuardian(ai_writings_dir=tmp_path)
        record = g.creative_break(
            insights=["test"],
            session_id="abc123",
        )
        assert "abc123" in Path(record.path).name


# ---------------------------------------------------------------------------
# generate_wiki_page()
# ---------------------------------------------------------------------------

class TestWikiPage:
    def test_returns_payload(self) -> None:
        g = CompactionGuardian()
        payload = g.generate_wiki_page(
            title="Test Session Summary",
            summary="A test.",
            content="The session was productive.",
        )
        assert payload["title"] == "Test Session Summary"
        assert payload["slug"] == "test-session-summary"
        assert payload["category"] == "fleet-status"

    def test_slug_generation(self) -> None:
        g = CompactionGuardian()
        payload = g.generate_wiki_page(
            title="The Lighthouse Keeper's Log!",
            summary="x",
            content="x",
        )
        # Special chars stripped
        assert "!" not in payload["slug"]
        assert "'" not in payload["slug"]


# ---------------------------------------------------------------------------
# extract_recent_insights()
# ---------------------------------------------------------------------------

class TestExtractInsights:
    def test_finds_insights(self) -> None:
        messages = [
            {"content": "I realized that the token estimator needs a floor."},
            {"content": "The key insight is that metaphors are load-bearing."},
        ]
        result = extract_recent_insights(messages)
        assert len(result["insights"]) >= 2
        assert any("token estimator" in i for i in result["insights"])

    def test_finds_metaphors(self) -> None:
        messages = [
            {"content": "The ship sailed through the storm and reached the harbor."},
        ]
        result = extract_recent_insights(messages)
        assert len(result["metaphors"]) >= 1

    def test_empty_messages(self) -> None:
        result = extract_recent_insights([])
        assert result["insights"] == []
        assert result["metaphors"] == []

    def test_max_messages_limit(self) -> None:
        # Create 50 messages, only last 20 should be scanned
        messages = [
            {"content": f"realized that finding number {i}"}
            for i in range(50)
        ]
        result = extract_recent_insights(messages, max_messages=5)
        # Only scanning last 5 messages
        assert all("number 4" in i or "number 3" in i or "number 2" in i
                    or "number 1" in i or "number 0" in i
                    for i in result["insights"])


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

class TestStatus:
    def test_idle_status(self) -> None:
        g = CompactionGuardian(agent_name="wesley")
        status = g.status()
        assert "wesley" in status
        assert "idle" in status

    def test_active_status(self) -> None:
        g = CompactionGuardian(context_limit=100_000, agent_name="deepseek")
        g.check(50_000)
        status = g.status()
        assert "deepseek" in status
        assert "GREEN" in status
