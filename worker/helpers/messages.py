MESSAGE_LIMIT = 30


def append_message(messages: list[dict], entry: dict) -> list[dict]:
    return [*messages, entry]


def format_transcript(messages: list[dict], limit: int = MESSAGE_LIMIT) -> str:
    lines = []
    for msg in messages[-limit:]:
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
        return complete.get("context") or {}
    start = last_message(messages, "questionnaire_start")
    if start:
        return {"business_about": start.get("content", "")}
    return {}
