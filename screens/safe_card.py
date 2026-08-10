# screens/safe_card.py
# Root cause of a real, confirmed Android crash: KivyMD's MDCard
# creates a graphics object (Fbo) for its ripple effect INSIDE
# __init__, using whatever self.size happens to be at that exact
# instant -- regardless of whether ripple_behavior is True or False
# (confirmed by reading KivyMD's actual source: init_fbos() runs
# unconditionally). Any MDCard built directly in Python and given no
# real size before construction gets size (0, 0) at that moment,
# which certain Android GPUs (confirmed via real crash logs: Mali
# chips) reject outright with "FBO Initialization failed: Incomplete
# attachment". This affects every popup/chip/card built in Python
# across the whole app.
#
# Fix: force a real, nonzero starting size to exist BEFORE
# MDCard.__init__ runs (by passing it through kwargs, which Kivy
# applies before the widget's own __init__ logic executes) instead of
# leaving it at the (0, 0) default. Every MDCard (or MDCard subclass)
# built in Python anywhere in this project should be created via
# make_safe_card(...) instead of calling the class directly.

from kivy.metrics import dp


def make_safe_card(card_class, **kwargs):
    # Only fills in a starting size if the caller didn't already
    # specify one -- doesn't override an intentional explicit size.
    if "size" not in kwargs:
        kwargs["size"] = (dp(1), dp(1))
    return card_class(**kwargs)