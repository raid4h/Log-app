"""
services/permissions_service.py

Reads the app's own actual runtime permission state on Android, so
the Settings > Privacy screen can show the user exactly what NoteNest
can currently access -- no network calls, nothing sent anywhere, just
asking the OS what's already been granted.

Only checks the three permissions buildozer.spec actually declares
(see its own android.permissions comment for the full reasoning):

- POST_NOTIFICATIONS   -- reminder/task notifications
                           (services/notification_service.py)
- READ_MEDIA_IMAGES     -- image-attach fallback for phones without
                           the Photo Picker (screens/editor/image_mixin.py)
- READ_EXTERNAL_STORAGE -- same fallback, pre-API-33 phones

On desktop (Windows/Linux, where `platform != "android"`), Android's
permission system doesn't exist at all -- every permission is reported
as "not_applicable" rather than granted/denied, since neither state is
real there. The screen using this service should show that as its own
distinct state, not lump it in with "denied".
"""

from kivy.utils import platform

PERMISSION_DEFINITIONS = [
    {
        "key": "notifications",
        "label": "Notifications",
        "description": "Lets Log alert you when a task or reminder is due.",
    },
    {
        "key": "read_media_images",
        "label": "Photos",
        "description": (
            "Only used as a fallback to attach images on older phones "
            "that don't have Android's built-in Photo Picker. Most "
            "devices never need this."
        ),
    },
    {
        "key": "read_external_storage",
        "label": "Storage (legacy)",
        "description": (
            "Same image-attach fallback as Photos, for phones on very "
            "old Android versions."
        ),
    },
]


def _android_permission_for(key):
    """
    Maps our own permission keys to the actual android.permissions.Permission
    constants. Imported lazily inside this function (not at module
    level) so this whole file can still be opened/edited on Windows --
    the `android` package only exists at runtime on an actual Android
    build, same reasoning screens/editor/image_mixin.py already uses
    for its own jnius/android imports.
    """
    from android.permissions import Permission

    return {
        "notifications": Permission.POST_NOTIFICATIONS,
        "read_media_images": Permission.READ_MEDIA_IMAGES,
        "read_external_storage": Permission.READ_EXTERNAL_STORAGE,
    }.get(key)


def is_android():
    return platform == "android"


def get_permission_statuses():
    """
    Returns a list of dicts, one per permission in PERMISSION_DEFINITIONS,
    each with an added "status" key:
      - "granted"        -- already allowed
      - "denied"         -- asked before (or declared in the manifest)
                             but not currently allowed
      - "not_applicable" -- not running on Android, so this concept
                             doesn't exist on this platform

    Never raises -- if checking a specific permission fails for any
    reason (e.g. running on an Android API level where a permission
    constant doesn't apply), that entry falls back to "not_applicable"
    rather than crashing the whole screen.
    """
    results = []

    if not is_android():
        for definition in PERMISSION_DEFINITIONS:
            results.append({**definition, "status": "not_applicable"})
        return results

    from android.permissions import check_permission

    for definition in PERMISSION_DEFINITIONS:
        try:
            android_permission = _android_permission_for(definition["key"])
            granted = check_permission(android_permission)
            status = "granted" if granted else "denied"
        except Exception:
            status = "not_applicable"
        results.append({**definition, "status": status})

    return results


def request_permission(key, on_result=None):
    """
    Triggers Android's own system permission dialog for a single
    permission. on_result(granted: bool), if given, is called once the
    user responds -- this is async, since the OS dialog isn't modal to
    our own code.

    No-op on non-Android platforms (nothing to request), and no-op if
    the key isn't one of ours.
    """
    if not is_android():
        return

    android_permission = _android_permission_for(key)
    if android_permission is None:
        return

    from android.permissions import request_permissions

    def _handle_result(permissions, grant_results):
        if on_result is not None:
            granted = bool(grant_results) and grant_results[0]
            on_result(granted)

    request_permissions([android_permission], _handle_result)


def open_app_settings():
    """
    Opens the OS's own "App info" screen for NoteNest -- the only way
    to grant a permission the user has permanently denied (checked
    "don't ask again"), since request_permission() silently does
    nothing once that's happened. No-op on non-Android platforms.

    Raises the underlying exception on failure rather than swallowing
    it -- the caller (privacy_settings_screen.py) is responsible for
    catching it and showing something visible instead of a hard
    crash. This used to crash with no visible cause; letting the
    exception surface here (instead of dying inside a bare pyjnius
    call with nothing catching it) means the caller can now show the
    real error text on-device tonight.
    """
    if not is_android():
        return

    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    Settings = autoclass("android.provider.Settings")
    Uri = autoclass("android.net.Uri")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")

    current_activity = PythonActivity.mActivity
    package_name = current_activity.getPackageName()

    intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
    uri = Uri.fromParts("package", package_name, None)
    intent.setData(uri)
    # FLAG_ACTIVITY_NEW_TASK is defensive: some p4a bootstraps/OEM
    # skins are inconsistent about whether mActivity's own context is
    # enough to start an Activity from here without it, and this
    # flag is harmless to set even when it isn't strictly required.
    intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    current_activity.startActivity(intent)