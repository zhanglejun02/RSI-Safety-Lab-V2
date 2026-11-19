"""Public task observation paging and declared context settings.

The outer tool interface pages large results. Context selection and pruning are
executable candidate resources (agents/default_context.py in the founder).
"""
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest

DEFAULT = {"max_bytes": 65536, "tool_page_chars": 6000,
           "keep_recent_messages": 3, "final_response_steps": 2}


def settings(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULT)
            or any(type(v) is not int or v < 1 for v in value.values())
            or not 16384 <= value["max_bytes"] <= 262144
            or value["tool_page_chars"] > 12000
            or value["keep_recent_messages"] > 8
            or value["final_response_steps"] > 3):
        raise ValidationError("Invalid bounded SEABench actor context")
    return dict(value)


class Context:
    def __init__(self, options):
        self.options = settings(options)

    def page(self, result, offset):
        content = result.get("content")
        if not isinstance(content, str):
            return result
        end = min(len(content), offset + self.options["tool_page_chars"])
        return {"ok": result["ok"], "content": content[offset:end],
                "offset": offset, "next_offset": end if end < len(content) else None,
                "total_chars": len(content), "content_sha256": digest(content),
                "truncated": offset > 0 or end < len(content)}
