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
# with content pinned near the bottom edge -- apply
# apply_bottom_inset_padding() wherever that's the case, not just
# terms_screen.

from kivy.utils import platform
from kivy.clock import Clock


def get_bottom_inset():
    """
    Returns the Android system navigation bar's height, in the same
    pixel space as Kivy's Window.size on Android (so it can be added
    directly to widget padding -- no dp() conversion needed).

    Returns 0 on any non-Android platform, and 0 (never raises) if
    insets can't be read for any reason -- e.g. Android versions
    before API 30, where WindowInsets.Type.navigationBars() doesn't
    exist yet, OR if the view hasn't been attached/laid out yet and
    getRootWindowInsets() returns None. That second case is common
    enough (seen reliably on MIUI/Xiaomi hardware, which dispatches
    window insets later relative to activity startup than stock
    Android) that a single call to this function right at screen-build
    time is NOT reliable on its own -- see apply_bottom_inset_padding()
    below, which retries instead of trusting one synchronous read.
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


def apply_bottom_inset_padding(widget, attempts=10, interval=0.05):
    """
    Pads `widget`'s bottom by the real system nav-bar inset, retrying
    a few frames apart instead of reading get_bottom_inset() once.

    WHY: on_kv_post runs exactly once per screen instance. A single
    synchronous get_bottom_inset() call there can catch the Android
    view tree before it's finished laying out and had insets
    dispatched to it -- which reads back as 0 and, because
    on_kv_post never runs again, permanently bakes in "no padding"
    for the lifetime of that screen instance, even though a real
    nonzero inset would have been available half a second later.
    This showed up specifically on a Xiaomi/MIUI device where insets
    dispatch later than on stock Android; retrying for up to ~0.5s
    covers that without any visible delay to the user.

    No-op (immediately, synchronously) on non-Android platforms.
    Safe to call from on_kv_post. `widget` must expose a `.padding`
    list of [left, top, right, bottom].
    """
    if platform != "android":
        return

    base_padding = list(widget.padding)

    def _try(attempts_left):
        inset = get_bottom_inset()
        if inset:
            left, top, right, bottom = base_padding
            widget.padding = [left, top, right, bottom + inset]
        elif attempts_left > 0:
            Clock.schedule_once(lambda dt: _try(attempts_left - 1), interval)
        # else: exhausted retries -- either this device genuinely has
        # no nav bar inset (fine, nothing to pad for), or insets never
        # became available for some other reason. Either way, padding
        # is left at its original value rather than looping forever.

    _try(attempts)