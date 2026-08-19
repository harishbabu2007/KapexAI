"""Focused regression tests for `QuestionnaireTool._is_real_idea`.

The classifier decides whether a user's first message is a real business idea
versus a questionnaire command, greeting, or gibberish. It must accept short
but meaningful business descriptions ("south indian restaurant in pune") while
still rejecting the trigger phrases it exists to block ("start the business
questionnaire"). The obvious cases are decided deterministically so an
unreliable LLM response can never block the questionnaire from starting.
"""

from types import SimpleNamespace

from conftest import run as _run

from worker.tools.questionnaire_tool import QuestionnaireTool


def _idea(text):
    tool = QuestionnaireTool()
    return _run(tool._is_real_idea(text))


# ── accepted: short but meaningful business ideas ────────────


def test_short_idea_south_indian_restaurant():
    assert _idea("south indian restaurant in pune")


def test_short_idea_coffee_shop():
    assert _idea("coffee shop in Pune")


def test_idea_open_coffee_shop():
    assert _idea("I want to open a coffee shop in Pune")


def test_idea_start_clothing_brand():
    assert _idea("I want to start a clothing brand")


def test_idea_sell_homemade_pickles():
    assert _idea("I want to sell homemade pickles online")


def test_idea_meal_planning_app():
    assert _idea("I want to build an app for meal planning")


def test_idea_open_bakery_bangalore():
    assert _idea("I want to open a bakery in Bangalore")


def test_idea_cloud_kitchen_mumbai():
    assert _idea("I want to start a cloud kitchen in Mumbai")


def test_idea_detail_targeting_college_students():
    assert _idea(
        "I want to open a South Indian restaurant in Pune targeting college students"
    )


def test_idea_with_greeting_prefix():
    assert _idea("hi i want to open south indian business in pune")


# ── rejected: commands, greetings, gibberish ─────────────────


def test_reject_start_business_questionnaire():
    assert not _idea("start the business questionnaire")


def test_reject_begin_questionnaire():
    assert not _idea("begin questionnaire")


def test_reject_plain_questionnaire():
    assert not _idea("questionnaire")


def test_reject_start():
    assert not _idea("start")


def test_reject_hi():
    assert not _idea("hi")


def test_reject_hello():
    assert not _idea("hello")


def test_reject_asdf():
    assert not _idea("asdf")


def test_reject_bla_bla():
    assert not _idea("bla bla")


# ── ambiguous middle still consults the LLM, but fails open ──


class _FakeTemplate:
    def __init__(self, content):
        self.content = content

    def __or__(self, _other):
        return self

    async def ainvoke(self, _kwargs):
        return SimpleNamespace(content=self.content)


AMBIGUOUS = "bakery"  # single 6-char word: reaches the LLM branch


def test_llm_parse_hiccup_accepts(monkeypatch):
    """A malformed LLM response in the ambiguous middle must not reject a
    plausible idea — it accepts, so the questionnaire can proceed."""
    monkeypatch.setattr(
        "worker.tools.questionnaire_tool.IS_IDEA_TEMPLATE",
        _FakeTemplate("not json at all"),
    )
    assert _idea(AMBIGUOUS)


def test_llm_valid_rejection_is_honoured(monkeypatch):
    monkeypatch.setattr(
        "worker.tools.questionnaire_tool.IS_IDEA_TEMPLATE",
        _FakeTemplate('{"real_idea": false}'),
    )
    assert not _idea(AMBIGUOUS)


def test_llm_valid_acceptance_is_honoured(monkeypatch):
    monkeypatch.setattr(
        "worker.tools.questionnaire_tool.IS_IDEA_TEMPLATE",
        _FakeTemplate('{"real_idea": true}'),
    )
    assert _idea(AMBIGUOUS)