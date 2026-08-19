# user_prefs.py
# A small local key-value store for lightweight user preferences (like
# whether the notes list opens in grid or list view). Kept in its own
# JSON file, separate from the database, since it's a device-local UI
# preference rather than actual note data -- same simple local-file
# pattern already used by trash_store.py.

import os
import json

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PREFS_FILE = os.path.join(_PROJECT_ROOT, "user_prefs.json")

_DEFAULTS = {
    "view_mode": "list",
    "recent_text_colors": [],
}


def _load_prefs():
    if not os.path.exists(PREFS_FILE):
        return dict(_DEFAULTS)
    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Fills in any preference key that didn't exist yet when this
        # file was first created, so adding a new preference later
        # doesn't require deleting an existing user's saved file.
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def get_pref(key):
    return _load_prefs().get(key, _DEFAULTS.get(key))


def set_pref(key, value):
    prefs = _load_prefs()
    prefs[key] = value
    with open(PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)