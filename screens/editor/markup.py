# screens/editor/markup.py
# Converts a note's plain-text formatting markers ({{img:...}},
# {{link:...}}, **bold**, __underline__, ==highlight==) into either
# real Kivy markup (for Preview mode) or clean plain text (for the
# notes-list preview and .txt export). Pure text transformation, no
# dependency on the screen itself.

import re
from kivy.utils import escape_markup
from urllib.parse import urlparse

# Matches an inline image marker, e.g. {{img:note_attachments/abc123.jpg}}
IMAGE_TOKEN_PATTERN = re.compile(r"\{\{img:(.*?)\}\}")
# Matches an inline hyperlink marker, e.g. {{link:https://example.com|click here}}
LINK_TOKEN_PATTERN = re.compile(r"\{\{link:(.*?)\|(.*?)\}\}", re.DOTALL)


def escape_and_apply_format_markup(text):
    # Assumes text has ALREADY been escape_markup()'d -- kept separate
    # from escaping so link conversion (which injects real markup tags)
    # can happen safely in between the two steps.
    text = re.sub(r"\*\*(.+?)\*\*", r"[b]\1[/b]", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"[u]\1[/u]", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*", r"[i]\1[/i]", text, flags=re.DOTALL)
    # Kivy's Label markup has no true background-highlight tag, so this
    # is approximated with a distinct text color -- a known, deliberate
    # simplification.
    text = re.sub(r"==(.+?)==", r"[color=#B8860B]\1[/color]", text, flags=re.DOTALL)
    return text


def convert_formatting_to_markup(text):
    # Plain formatting-only conversion, no link support -- kept
    # available for any future caller that just needs this.
    return escape_and_apply_format_markup(escape_markup(text))


def strip_markers_for_export(raw_content):
    # Turns raw stored note text into clean plain text: used for BOTH
    # the notes-list preview and .txt export, so a fix here (like the
    # link-stripping line below) only has to happen once instead of
    # two separate copies drifting out of sync.
    text = IMAGE_TOKEN_PATTERN.sub("[Photo]", raw_content)
    # Links show as just their visible label -- e.g.
    # {{link:https://x.com|click here}} becomes "click here", not the
    # raw marker or the URL. (This was previously missing entirely --
    # links used to leak into previews/exports as raw markers.)
    text = LINK_TOKEN_PATTERN.sub(lambda m: m.group(2), text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"==(.+?)==", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*", r"\1", text, flags=re.DOTALL)
    return text.strip()

def convert_markers_to_html(raw_content, image_to_html):
    """
    Converts a note's raw stored text (with {{img:...}}, {{link:...}},
    **bold**, __underline__, *italic*, ==highlight== markers) into an
    HTML fragment, used by the "export as HTML" feature.

    image_to_html: a function that takes the stored image path
    captured from a {{img:...}} marker and returns the HTML to put in
    its place (a real <img> tag). Passed in rather than handled here,
    so this file can stay pure text transformation -- reading image
    files off disk and encoding them is left to the caller.
    """
    # Escape HTML-sensitive characters FIRST, then inject real tags --
    # same order as escape_and_apply_format_markup above, so escaping
    # can't accidentally mangle a tag we just inserted.
    text = (
        raw_content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    text = IMAGE_TOKEN_PATTERN.sub(lambda m: image_to_html(m.group(1)), text)
    text = LINK_TOKEN_PATTERN.sub(
        lambda m: f'<a href="{m.group(1)}">{m.group(2)}</a>', text
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text, flags=re.DOTALL)
    text = re.sub(
        r"==(.+?)==",
        r'<span style="background-color:#FFF3B0">\1</span>',
        text, flags=re.DOTALL,
    )
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text, flags=re.DOTALL)
    # Plain newlines don't create line breaks in HTML -- convert them
    # to <br> explicitly so paragraph breaks in the note are kept.
    text = text.replace("\n", "<br>\n")
    return text

def extract_domain_label(url):
    """Best-effort short label from a URL, e.g.
    'https://www.youtube.com/watch?v=x' -> 'youtube.com'. Used to
    auto-fill the link display-text field when the user hasn't typed
    a custom one themselves. Falls back to 'Link' if the string isn't
    really URL-shaped yet (e.g. still empty or mid-typing)."""
    url = url.strip()
    if not url:
        return ""
    # urlparse needs a scheme to correctly split out the domain --
    # if the user hasn't typed http(s):// yet, add one temporarily
    # just for this parse (doesn't affect what gets saved).
    candidate = url if "://" in url else f"https://{url}"
    try:
        netloc = urlparse(candidate).netloc
    except ValueError:
        netloc = ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or "Link"