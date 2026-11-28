import json

import pytest

from distilhead.cli import main
from distilhead.pack.validate import validate


def test_toy_pack_valid(toy):
    assert validate(toy) == []


def edit(p, old, new):
    t = p.read_text()
    assert old in t
    p.write_text(t.replace(old, new))


@pytest.mark.parametrize(
    "file,old,new,frag",
    [
        ("pack.yaml", "cap_usd: 5", "cap_usd: 50", "cap_usd"),
        ("pack.yaml", "cap_usd: 5", "cap_usd: 0", "cap_usd"),
        ("pack.yaml", "label_set: level", "label_set: nope", "unknown label_set"),
        (
            "pack.yaml",
            "opposed: [[negative], [positive]]",
            "opposed: [[negative], [bogus]]",
            "bogus",
        ),
        ("pack.yaml", "providers: [gemini]", "providers: [xai]", "hard-denied"),
        ("pack.yaml", "providers: [gemini]", "providers: [mistral]", "terms record"),
        (
            "heldout.yaml",
            'id: h3, text: "The report is stored in the shared folder."',
            'id: h3, text: "The meeting is on the calendar for next month."',
            "also in corpus",
        ),
        ("reference.jsonl", '"label": "positive"', '"label": "great"', "not in label set"),
        ("prototypes.yaml", 'high: ["Do this right now."]', "high: []", "missing urgency/high"),
        ("prompt.md", "quote", "excerpt", "quote"),
    ],
)
def test_invalid_packs_fail(toy, file, old, new, frag):
    edit(toy / file, old, new)
    errs = validate(toy)
    assert errs and any(frag in e for e in errs), errs


def test_missing_file(toy):
    (toy / "bar.yaml").unlink()
    assert any("missing file" in e for e in validate(toy))


def test_extra_keys_refused(toy):
    edit(toy / "pack.yaml", "schema_version: 1", "schema_version: 1\nsurprise: true")
    assert validate(toy)


def test_cli_exit_codes(toy, tmp_path):
    assert main(["pack-validate", str(toy)]) == 0
    (toy / "bar.yaml").unlink()
    assert main(["pack-validate", str(toy)]) == 1


def test_run_end_to_end_offline(toy, tmp_path):
    from conftest import REPO

    assert main(["run", str(toy), "--out", str(tmp_path / "o"), "--repo", str(REPO)]) == 0
    m = json.loads((tmp_path / "o" / "pack" / "manifest.json").read_text())
    assert m["status"] == "complete" and m["pack"]["id"] == "toy"


def test_empty_denylist(toy):
    (toy / "denylist.txt").write_text("# empty\n")
    assert any("denylist is empty" in e for e in validate(toy))
