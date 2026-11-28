import re

from conftest import REPO

SDKS = re.compile(
    r"^\s*(?:import|from)\s+(?:google\.genai|google\.generativeai|openai|anthropic|xai_sdk|httpx|requests)\b",
    re.MULTILINE,
)


def test_only_teacher_imports_provider_sdks():
    bad = []
    for p in (REPO / "src").rglob("*.py"):
        if p.name == "teacher.py" and p.parent.name == "guard":
            continue
        if SDKS.search(p.read_text()):
            bad.append(str(p.relative_to(REPO)))
    assert bad == []
