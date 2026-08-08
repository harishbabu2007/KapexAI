class Tool:
    """Base class for plug-and-play tools.

    To add a new capability: subclass, set `name`, `description`, `example` and
    `suggestion`, implement `run`, and register it in `worker/tools/registry.py`.
    """

    name: str = ""
    description: str = ""
    example: str = ""
    suggestion: str = ""
    # True when the tool needs the completed questionnaire's business context
    # (e.g. SWOT, research). The router refuses to dispatch such tools until the
    # questionnaire has been completed.
    requires_context: bool = False

    def run(self, state: dict) -> list[dict]:
        """Handle the current user message.

        Return a list of message log entries to persist and stream. Each entry
        is a dict with at least {"role", "agent", "type", "content", ...}.
        The extra keys define the message's own JSON format. May be sync or async.
        """
        raise NotImplementedError
