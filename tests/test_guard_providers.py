import pytest
import yaml

from distilhead.guard.providers import ProviderRefused, check_provider


def test_default_allowed(toy):
    check_provider("gemini", ["gemini"], toy)
    check_provider("Gemini", ["gemini"], toy)


@pytest.mark.parametrize("p", ["xai", "XAI", "openai"])
def test_denied_even_if_allowlisted(toy, p):
    with pytest.raises(ProviderRefused, match="hard-denied"):
        check_provider(p, [p], toy)


def test_not_in_allowlist(toy):
    with pytest.raises(ProviderRefused, match="allowlist"):
        check_provider("other", ["gemini"], toy)


def test_terms_record_required_and_complete(toy):
    with pytest.raises(ProviderRefused, match="terms record"):
        check_provider("other", ["other"], toy)
    rec = toy / "terms" / "other.yaml"
    rec.write_text(yaml.dump({"clause_url": "https://example.com/t"}))
    with pytest.raises(ProviderRefused, match="missing fields"):
        check_provider("other", ["other"], toy)
    rec.write_text(
        yaml.dump({"clause_url": "https://example.com/t", "date": "2026-01-01", "summary": "ok"})
    )
    check_provider("other", ["other"], toy)
