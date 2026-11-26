from conftest import REPO

from distilhead import checkcore


def _denylists():
    return sorted((REPO / "packs").glob("*/denylist.txt"))


def test_denylists_exist_and_nonempty():
    dls = _denylists()
    assert dls
    for d in dls:
        assert checkcore.load_denylist(d)


def test_core_has_no_domain_strings():
    assert checkcore.scan(REPO, _denylists()) == []


def test_scanner_catches_hits_and_stems(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 'Foobarian'\ny = 'xfoo'\n")
    dl = tmp_path / "dl.txt"
    dl.write_text("Foobar*\nfoo\n")
    for d in ("tests", "tools", ".github", "packs/toy"):
        (tmp_path / d).mkdir(parents=True)
    hits = checkcore.scan(tmp_path, [dl])
    assert len(hits) == 1 and "a.py:1" in hits[0]


def test_empty_denylist_refused(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        checkcore.compile_denylist([])
