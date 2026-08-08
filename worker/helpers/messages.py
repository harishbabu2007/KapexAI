import json

MESSAGE_LIMIT = 30

BUSINESS_PROFILE_TYPE = "business_profile"

# The canonical keys of the user's business profile. Only non-empty values are
# kept, so a fresh profile is indistinguishable from a missing one.
BUSINESS_PROFILE_KEYS = (
    "your_name",
    "industry",
    "about_you",
    "business_history",
    "location",
    "monthly_income",
    "monthly_expenditure",
)


def append_message(messages: list[dict], entry: dict) -> list[dict]:
    return [*messages, entry]


def format_transcript(messages: list[dict], limit: int = MESSAGE_LIMIT) -> str:
    lines = []
    profile = business_profile(messages)
    if profile:
        lines.append(f"SYSTEM (business_profile): {json.dumps(profile)}")
    for msg in messages[-limit:]:
        if msg.get("type") == BUSINESS_PROFILE_TYPE:
            continue
        role = msg.get("role", "?")
        msg_type = msg.get("type", "")
        content = msg.get("content", "")
        lines.append(f"{role} ({msg_type}): {content}")
    return "\n".join(lines)


def last_message(messages: list[dict], msg_type: str) -> dict | None:
    for msg in reversed(messages):
        if msg.get("type") == msg_type:
            return msg
    return None


def business_profile(messages: list[dict]) -> dict:
    """Returns the injected business profile (if any), scanning the whole log so
    it is found even after long conversations push the entry out of the tail."""
    for msg in reversed(messages):
        if msg.get("type") == BUSINESS_PROFILE_TYPE:
            profile = msg.get("profile") or {}
            return profile if isinstance(profile, dict) else {}
    return {}


def inject_business_profile(messages: list[dict], profile: dict) -> list[dict]:
    """Drops any stale profile entry (from a cached state) and prepends a fresh
    one carrying the user's current profile. Empty profiles are dropped entirely
    so a user without context behaves exactly like before."""
    messages = [m for m in messages if m.get("type") != BUSINESS_PROFILE_TYPE]
    if not profile or not isinstance(profile, dict):
        return messages
    filled = {k: str(profile.get(k) or "").strip() for k in BUSINESS_PROFILE_KEYS}
    filled = {k: v for k, v in filled.items() if v}
    if not filled:
        return messages
    return [
        {
            "role": "SYSTEM",
            "agent": "PROFILE",
            "type": BUSINESS_PROFILE_TYPE,
            "content": "",
            "profile": filled,
        },
        *messages,
    ]


def questionnaire_pending(messages: list[dict]) -> bool:
    """True when the questionnaire tool asked questions and they have not been
    answered yet."""
    pending = False
    for msg in messages:
        msg_type = msg.get("type")
        if msg_type == "questionnaire":
            pending = True
        elif msg_type == "questionnaire_answer":
            pending = False
    return pending


def questionnaire_complete(messages: list[dict]) -> bool:
    """True when the questionnaire has been finished (a `questionnaire_complete`
    entry exists). Tools that need business context must not run until this is
    true — the router gates them on it."""
    return last_message(messages, "questionnaire_complete") is not None


def business_context(messages: list[dict]) -> dict:
    complete = last_message(messages, "questionnaire_complete")
    if complete:
        context = complete.get("context") or {}
    else:
        start = last_message(messages, "questionnaire_start")
        context = {"business_about": start.get("content", "")} if start else {}

    profile = business_profile(messages)
    if profile:
        context = {**context, "business_profile": profile}
    return context
