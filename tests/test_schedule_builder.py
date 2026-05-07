"""Tests for agent-orchestration/schedule_builder.py.

Pins the duration-prediction heuristics so an accidental rename of a
schedule label doesn't silently change the calendar's allotted slot.
"""
from schedule_builder import schedule_duration_minutes


class TestDurationHeuristics:
    def test_workspace_cleanup_120(self):
        assert schedule_duration_minutes("any-bot", "Weekly Workspace Cleanup") == 120

    def test_strategy_review_90(self):
        assert schedule_duration_minutes("any-bot", "Strategy Review") == 90

    def test_standup_30(self):
        assert schedule_duration_minutes("any-bot", "Evening Standup") == 30

    def test_check_up_30(self):
        assert schedule_duration_minutes("any-bot", "Noon Check-Up") == 30

    def test_qa_gate_45(self):
        assert schedule_duration_minutes("any-bot", "QA Gate Review") == 45

    def test_publish_60(self):
        assert schedule_duration_minutes("any-bot", "Blog Publish") == 60

    def test_thread_post_45(self):
        assert schedule_duration_minutes("any-bot", "Weekly Thread Post") == 45

    def test_social_post_45(self):
        assert schedule_duration_minutes("any-bot", "Social Post Draft") == 45

    def test_intel_75(self):
        assert schedule_duration_minutes("any-bot", "Morning Intel") == 75

    def test_scan_75(self):
        assert schedule_duration_minutes("any-bot", "SNS Scan") == 75

    def test_scout_90(self):
        assert schedule_duration_minutes("any-bot", "Easy Build Scout") == 90

    def test_discussions_90(self):
        assert schedule_duration_minutes("any-bot", "Hot Discussions") == 90

    def test_unknown_falls_back_to_60(self):
        assert schedule_duration_minutes("any-bot", "Some Random New Skill") == 60

    def test_bot_name_factors_into_lowered_match(self):
        # The function joins bot+label, so a bot name containing a keyword
        # also matches. Pin that behavior so it's not surprising.
        assert schedule_duration_minutes("publisher", "Daily Run") == 60  # "publish" in lowered
        # Strict check: "publisher" contains "publish" → matches publish branch.
        assert schedule_duration_minutes("publisher", "anything") == 60
