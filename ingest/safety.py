"""Prompt-injection hygiene for untrusted documents.

Uploaded documents end up inside LLM prompts (planner, reranker, reflector, answerer), so their text is untrusted input.
Two helpers:

* `scan(text)`: flags instruction-like content at ingest time. It only *reports*; blocking would break legitimate
  security write-ups, and a regex list can never be complete, so it is a signal for the UI and for humans, not a gate.
* `sanitize(text)`: neutralises the two things that let a passage break out of its frame inside a prompt: hidden
  control characters and our own delimiter tags.

See README "Prompt-injection threat model" for what is and is not defended.
"""
import re

HIDDEN = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")

PATTERNS = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|system|all|any)\b"
        r"[^.\n]{0,30}\b(instructions?|prompts?|rules?|guidelines?|context)\b", re.I),
    "role_override": re.compile(
        r"\byou are (now|no longer)\b|\bnew (instructions?|persona|system prompt)\b|\bfrom now on,? (you|always|only)\b", re.I),
    "prompt_extraction": re.compile(
        r"\b(reveal|print|repeat|show|output|leak)\b[^.\n]{0,30}\b(system prompt|your (instructions|rules|prompt))", re.I),
    "chat_markup": re.compile(r"<\|(im_start|im_end|system|assistant|user)\|>|\[/?INST\]|<</?SYS>>|^\s*(system|assistant)\s*:", re.I | re.M),
    "output_directive": re.compile(r"\b(reply|respond|answer|say|output|write)\b[^.\n]{0,20}\b(only|exactly|verbatim)\b", re.I),
    "markdown_image": re.compile(r"!\[[^\]]*\]\(\s*https?://[^)]*\)"),
}


def scan(text: str) -> dict[str, int]:
    """{pattern name: occurrences} for everything that matched; empty when the text looks clean."""
    found = {name: len(rx.findall(text)) for name, rx in PATTERNS.items()}
    found["hidden_characters"] = len(HIDDEN.findall(text))
    return {k: v for k, v in found.items() if v}


_TAG = re.compile(r"<\s*(/?)\s*(source|sources|passage|passages)\b", re.I)


def sanitize(text: str) -> str:
    """Remove hidden control characters and defuse our own delimiter tags so a passage cannot close its frame."""
    text = HIDDEN.sub("", text)
    return _TAG.sub(lambda m: f"‹{m.group(1)}{m.group(2)}", text)
