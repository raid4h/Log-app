[app]

# (str) Title of your application
title = Log

# (str) Package name
package.name = log

# (str) Package domain (needed for android/ios packaging)
# Reverse-DNS style; doesn't need to resolve to a real domain, it just
# has to be unique and MUST NOT change once you've done a real release
# (Android identifies the app by package.domain + package.name).
package.domain = org.cse299

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf,json

# (list) List of directories to exclude (let empty to not exclude anything)
source.exclude_dirs = .buildozer,bin,.git,.vscode,__pycache__,tests

# (list) List of exclusions using pattern matching
# Dev-machine-only artifacts that must never end up bundled in the APK:
# the local SQLite DB (a fresh one is created on first run on-device),
# locally-picked note attachments/exports, test scripts/fixtures, the
# device-local Terms & Conditions agreement record (shouldn't ship
# pre-populated), and the temporary debug log (removed from the code,
# excluded here defensively too).
source.exclude_patterns = MyApp.db,theme_prefs.json,user_prefs.json,trash.json,note_attachments/*,exported_notes/*,test_*.py,test_backup.json,tempCodeRunnerFile.py,legal_prefs.json,backup_debug.log

# (str) Application versioning
version = 0.1

# (list) Application requirements
# KivyMD has no stable 2.0 release on PyPI (this app relies on 2.0-only
# APIs such as MDButton/MDButtonText), so it's pinned to an exact commit
# via a bare GitHub zip URL (not kivymd==https://... -- that form makes
# p4a write a broken requirements.txt that pip treats as a local path).
# Keep the commit hash in sync with requirements.txt at the repo root.
requirements = python3,kivy==2.3.1,https://github.com/kivymd/KivyMD/archive/dbe8ad4619ae942e3485a8f8f5eff295c4cb1db7.zip,pillow==10.4.0,materialyoucolor==3.0.3,asynckivy==0.6.4,asyncgui==0.6.3,plyer==2.1.0,requests==2.31.0

# (str) Presplash of the application
# TODO(design): add assets/presplash.png (recommended 2048x2048, will be
# letterboxed to fit every device aspect ratio). Build works without it
# -- p4a falls back to a plain white splash -- but this path is where it
# goes once it exists. Keep commented until the file is present; a
# missing path makes packaging crash instead of using the fallback.
#presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon of the application
# TODO(design): add assets/icon.png (512x512 recommended). Build works
# without it -- p4a falls back to the default Kivy icon -- but this path
# is where it goes once it exists. Keep commented until the file is present.
icon.filename = %(source.dir)s/assets/icon.png

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
# NoteNest's screens aren't built with a landscape layout, so lock to
# portrait rather than fighting rotation bugs. Revisit if that changes.
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
# - READ_EXTERNAL_STORAGE: the manual backup export/import screen
#   (services/manual_export.py) lets the user pick an arbitrary save/load
#   location via plyer's native file picker. Capped at API 32 -- from
#   API 33 Android splits this into per-media-type permissions.
# - READ_MEDIA_IMAGES: the API 33+ replacement, needed for the file
#   picker to actually see photos when attaching images to a note.
# - POST_NOTIFICATIONS: required on Android 13+ (API 33+) for the
#   reminder notifications sent from services/notification_service.py.
# WRITE_EXTERNAL_STORAGE is deliberately omitted -- it is a no-op from
# Android 11 (API 30) onward under scoped storage.
# Note attachments and the app's own SQLite DB should live under
# App.user_data_dir (private app storage), which needs no permission --
# see the app-side compatibility workstream for that path migration.
android.permissions = POST_NOTIFICATIONS,(name=android.permission.READ_MEDIA_IMAGES;maxSdkVersion=35),(name=android.permission.READ_EXTERNAL_STORAGE;maxSdkVersion=32)

# (int) Target Android API, should be as high as possible.
android.api = 35

# (int) Minimum API your APK / AAB will support.
android.minapi = 24

# (str) Android NDK version to use
android.ndk = 25b

# (int) Android SDK build-tools version to use
# Must be >= android.api, otherwise the packaging step fails looking for
# an aapt2/d8 that can compile API 35 resources.
android.build_tools = 35.0.0

# (list) The Android archs to build for
# Covers essentially all real devices in active use; drop armeabi-v7a
# later if you want a smaller/faster build and don't need old-device
# support for grading/demo.
android.archs = arm64-v8a,armeabi-v7a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) The format used to package the app for release mode (aab or apk).
# apk for sideloading and demo. Switch to aab only if the app is ever
# uploaded to Google Play, which requires that format.
android.release_artifact = apk

# (str) The format used to package the app for debug mode (apk or aar).
android.debug_artifact = apk


[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
