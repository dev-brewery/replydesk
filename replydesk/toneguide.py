"""Parse the owner's tone guide text (lenient format, ARCHITECTURE §2)."""

from replydesk.model import ToneGuide

_VOICE = "# VOICE"
_FACTS = "# FACTS I'LL STAND BEHIND"


class ToneGuideError(ValueError):
    """Raised when the tone guide text is empty or whitespace-only."""


def _is_heading(line: str, heading: str) -> bool:
    return line.strip().lower().startswith(heading.lower())


def parse_tone_guide(text: str) -> ToneGuide:
    if not text or not text.strip():
        raise ToneGuideError("tone guide text is empty")
    voice_lines: list[str] = []
    facts: list[str] = []
    in_facts = False
    for raw in text.splitlines():
        line = raw.strip()
        if _is_heading(line, _FACTS):
            in_facts = True
        elif _is_heading(line, _VOICE):
            in_facts = False
        elif line:
            if in_facts:
                facts.extend(_split_fact(line))
            else:
                voice_lines.append(line)
    if in_facts and not facts:
        pass  # facts heading with nothing under it is fine
    return ToneGuide(voice="\n".join(voice_lines), facts=tuple(facts))


def _split_fact(line: str) -> list[str]:
    if line.startswith(("-", "*", "•")):
        line = line[1:].strip()
        return [line] if line else []
    # prose: split on sentence ends
    parts = [p.strip() for p in line.replace("!.", "!").split(". ") if p.strip()]
    out = []
    for p in parts:
        p = p.rstrip(".").strip()
        if p:
            out.append(p)
    return out
