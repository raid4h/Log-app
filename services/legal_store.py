# services/legal_store.py
#
# A small local key-value store recording whether the user has agreed
# to NoteNest's Terms & Conditions, and which VERSION of those terms
# they agreed to. Kept in its own JSON file, separate from the
# database, same simple local-file pattern already used by
# user_prefs.py and trash_store.py.
#
# The version number matters: if the terms are ever edited later,
# bumping TERMS_VERSION (in legal_content.py) means an existing user
# who already agreed to an OLDER version will be asked to agree again
# on their next launch, rather than the app silently assuming their
# old agreement still covers new terms they never actually saw.

import os
import json

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_PROJECT_ROOT)  # up one level, out of services/
LEGAL_FILE = os.path.join(_PROJECT_ROOT, "legal_prefs.json")

_DEFAULTS = {
    "agreed": False,
    "agreed_version": None,
    "agreed_at": None,
}


def _load():
    if not os.path.exists(LEGAL_FILE):
        return dict(_DEFAULTS)
    try:
        with open(LEGAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Fills in any key that didn't exist yet when this file was
        # first created, so adding a new field later doesn't require
        # deleting an existing user's saved file.
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def _save(data):
    with open(LEGAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def has_agreed_to_version(version):
    """
    True only if the user has agreed, AND the version they agreed to
    matches the version passed in exactly -- an agreement to an older
    version never counts as covering a newer one.
    """
    data = _load()
    return bool(data["agreed"]) and data["agreed_version"] == version


def record_agreement(version):
    """Records that the user just agreed to the given terms version, now."""
    from datetime import datetime, timezone
    _save({
        "agreed": True,
        "agreed_version": version,
        "agreed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


def clear_agreement():
    """
    Resets agreement state entirely. Not used by normal app flow --
    kept for completeness/testing (e.g. manually forcing the terms
    screen to reappear without bumping the version number).
    """
    _save(dict(_DEFAULTS))