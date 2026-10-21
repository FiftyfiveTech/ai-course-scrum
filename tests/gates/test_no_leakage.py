"""
Gate: dev ∩ heldout = ∅ by content hash.

Checks that no update in evals/heldout/ appears in evals/dev/ (by sha256 of
the raw field), so the Builder cannot have tuned on held-out cases.

Done when:
  - Test FAILS when a held-out update is planted in dev/
  - A vacuous PASS (either set empty) is reported loudly and the test fails

Run:
  pytest tests/gates/test_no_leakage.py -v
"""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
DEV_DIR = REPO_ROOT / "evals" / "dev"
HELDOUT_DIR = REPO_ROOT / "evals" / "heldout"


def _load_updates(directory: Path) -> list[dict]:
    """Load all updates from every JSON file in a directory."""
    updates = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        if isinstance(data, list):
            updates.extend(data)
        else:
            updates.append(data)
    return updates


def _raw_hash(update: dict) -> str:
    """sha256 of the normalised raw field (stripped, lowercased whitespace)."""
    raw = " ".join(update["raw"].split()).lower()
    return hashlib.sha256(raw.encode()).hexdigest()


def test_no_leakage():
    dev_updates = _load_updates(DEV_DIR)
    heldout_updates = _load_updates(HELDOUT_DIR)

    # Vacuous pass guard — if either set is empty the test cannot be trusted.
    assert len(dev_updates) > 0, (
        "VACUOUS PASS DETECTED: evals/dev/ contains no updates. "
        "Add labelled examples before this gate can count."
    )
    assert len(heldout_updates) > 0, (
        "VACUOUS PASS DETECTED: evals/heldout/ contains no updates. "
        "Seal the held-out set before this gate can count."
    )

    dev_hashes = {_raw_hash(u): u["id"] for u in dev_updates}
    heldout_hashes = {_raw_hash(u): u["id"] for u in heldout_updates}

    overlap = set(dev_hashes) & set(heldout_hashes)

    if overlap:
        leaked = [
            f"  dev:{dev_hashes[h]}  ==  heldout:{heldout_hashes[h]}"
            for h in overlap
        ]
        raise AssertionError(
            f"LEAKAGE DETECTED — {len(overlap)} held-out update(s) found in dev set:\n"
            + "\n".join(leaked)
        )

    print(
        f"no_leakage: dev={len(dev_updates)} updates, "
        f"heldout={len(heldout_updates)} updates, "
        f"overlap=0  PASS"
    )
