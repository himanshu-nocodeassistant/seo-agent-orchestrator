"""
SDK compatibility patch for claude_agent_sdk.

Monkey-patches the SDK's internal message parser so unknown message types
(e.g. rate_limit_event) are silently skipped instead of raising MessageParseError.

Import this module before using claude_agent_sdk.query() or ClaudeSDKClient.
It is idempotent — safe to import multiple times.
"""

import logging

logger = logging.getLogger(__name__)

_patched = False


def apply_safe_parse_patch() -> None:
    """Apply the safe message parse patch to claude_agent_sdk internals.

    Must be called before any SDK usage. Idempotent.
    """
    global _patched
    if _patched:
        return

    try:
        from claude_agent_sdk._errors import MessageParseError
        import claude_agent_sdk._internal.message_parser as _mp
        import claude_agent_sdk._internal.client as _mc

        _original_parse = _mp.parse_message

        def _safe_parse_message(data):
            try:
                return _original_parse(data)
            except MessageParseError as e:
                if "Unknown message type" in str(e):
                    logger.warning(
                        "Skipping unknown SDK message type '%s'",
                        data.get("type"),
                    )
                    return None
                raise

        _mp.parse_message = _safe_parse_message
        _mc.parse_message = _safe_parse_message  # patch the already-imported reference
        _patched = True
        logger.debug("claude_agent_sdk safe-parse patch applied")
    except Exception as exc:
        logger.warning("Could not apply SDK safe-parse patch: %s", exc)


# Apply automatically on import so consumers only need `import agent.sdk_compat`
apply_safe_parse_patch()
