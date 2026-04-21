"""JSON extraction and repair from freeform LLM text.

The 8B model frequently produces malformed JSON. This module provides
robust extraction and repair mechanisms.
"""

import json
import re


def extract_json(text: str) -> dict | list | None:
    """Extract the first valid JSON object or array from text.

    Tries multiple strategies:
    1. Look for ```json ... ``` code blocks
    2. Find outermost { } or [ ] by bracket matching
    3. Attempt repair if parsing fails

    Returns parsed JSON or None if extraction fails.
    """
    if not text or not text.strip():
        return None

    # Strategy 1: Look for ```json code blocks
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            # Try repair on the code block content
            repaired = repair_json(code_block_match.group(1).strip())
            if repaired is not None:
                return repaired

    # Strategy 2: Bracket matching for first { or [
    raw = _extract_bracketed(text)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            repaired = repair_json(raw)
            if repaired is not None:
                return repaired

    # Strategy 3: Try parsing the entire text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        repaired = repair_json(text.strip())
        if repaired is not None:
            return repaired

    return None


def repair_json(text: str) -> dict | list | None:
    """Attempt common repairs on malformed JSON.

    Fixes:
    - Trailing commas before } or ]
    - Single quotes instead of double quotes
    - Unquoted keys
    - Truncated JSON (missing closing brackets)
    - Comments
    """
    if not text:
        return None

    repaired = text

    # Remove single-line comments
    repaired = re.sub(r"//[^\n]*", "", repaired)

    # Remove multi-line comments
    repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)

    # Fix trailing commas before } or ]
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    # Try parsing after basic fixes
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Fix single quotes to double quotes (careful with apostrophes in text)
    try:
        fixed_quotes = _fix_quotes(repaired)
        return json.loads(fixed_quotes)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try adding missing closing brackets
    try:
        closed = _close_brackets(repaired)
        return json.loads(closed)
    except json.JSONDecodeError:
        pass

    return None


def _extract_bracketed(text: str) -> str | None:
    """Extract first balanced { } or [ ] block using bracket matching."""
    start = -1
    open_char = None

    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            open_char = ch
            break

    if start == -1:
        return None

    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            if in_string:
                escape = True
            continue

        if ch == '"' and not escape:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    # If we never balanced, return what we have (will try repair)
    if depth > 0:
        return text[start:]

    return None


def _fix_quotes(text: str) -> str:
    """Replace single quotes with double quotes for JSON keys and string values.

    This is a simplified fix that works for most LLM outputs.
    """
    # Replace single-quoted keys: 'key': -> "key":
    result = re.sub(r"'([^']*?)'\s*:", r'"\1":', text)
    # Replace single-quoted values: : 'value' -> : "value"
    result = re.sub(r":\s*'([^']*?)'", r': "\1"', result)
    return result


def _close_brackets(text: str) -> str:
    """Add missing closing brackets/braces to truncated JSON."""
    stack = []
    in_string = False
    escape = False

    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    # Close any unclosed brackets
    result = text.rstrip()
    # Remove trailing comma before closing
    result = re.sub(r",\s*$", "", result)
    for closer in reversed(stack):
        result += closer

    return result
