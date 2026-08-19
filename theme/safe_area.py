# theme/safe_area.py
#
# Android 15 (API 35) enforces edge-to-edge layout by default -- app
# content draws behind the system status bar AND the gesture
# navigation bar unless the app explicitly reads those insets and
# pads around them. Without this, bottom-pinned buttons (see
# terms_screen.kv) can render partially or fully underneath the
# translucent gesture bar -- on phones using gesture navigation
# (no visible back/home buttons), taps in that zone are consumed by
# the OS's back-swipe gesture detection instead of reaching the
# button underneath it, even though the button is visibly on-screen.
#
# buildozer.spec sets android.api = 35, so this affects every screen
# with content pinned near the bottom edge -- apply get_bottom_inset()
# wherever that's the case, not just terms_screen.

from kivy.utils import platform


def get_bottom_inset():
    """
    Returns the Android system navigation bar's height, in the same
    pixel space as Kivy's Window.size on Android (so it can be added
    directly to widget padding -- no dp() conversion needed).

    Returns 0 on any non-Android platform, and 0 (never raises) if
    insets can't be read for any reason -- e.g. Android versions
    before API 30, where WindowInsets.Type.navigationBars() doesn't
    exist yet. This runs during screen setup, so it must never crash
    a screen that would otherwise render fine.
    """
    if platform != "android":
        return 0

    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        decor_view = activity.getWindow().getDecorView()
        insets = decor_view.getRootWindowInsets()
        if insets is None:
            return 0

        WindowInsetsType = autoclass("android.view.WindowInsets$Type")
        nav_bars = insets.getInsets(WindowInsetsType.navigationBars())
        return nav_bars.bottom
    except Exception:
        return 0