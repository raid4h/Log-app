# screens/editor/paths.py
import os
from kivy.app import App

def _project_root():
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(this_dir))

def _writable_root():
    app = App.get_running_app()
    if app is not None:
        return app.user_data_dir
    return _project_root()

PROJECT_ROOT = _project_root()
FONTS_DIR = os.path.join(PROJECT_ROOT, "fonts")  # read-only bundled asset, fine as a constant

def get_attachments_dir():
    return os.path.join(_writable_root(), "note_attachments")

def get_exports_dir():
    return os.path.join(_writable_root(), "exported_notes")

DEFAULT_NOTEBOOK_ID = 1