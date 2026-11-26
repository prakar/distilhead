import pytest

from distilhead import barlock


def test_lock_verify_and_tamper(toy):
    with pytest.raises(barlock.BarLockError):
        barlock.verify(toy)
    h = barlock.lock(toy)
    assert barlock.verify(toy) == h
    barlock.lock(toy)  # idempotent
    (toy / "bar.yaml").write_text((toy / "bar.yaml").read_text().replace("0.8", "0.1"))
    with pytest.raises(barlock.BarLockError):
        barlock.verify(toy)
    with pytest.raises(barlock.BarLockError):
        barlock.lock(toy)
