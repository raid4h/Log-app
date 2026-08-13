# NoteNest

## Android build environment setup

Buildozer only runs on Linux/macOS (it shells out to Linux-only Android
build tooling), so on Windows you build through **WSL2**, not native
Windows Python. These steps take you from a clean WSL Ubuntu install to
a working debug APK. Run everything below **inside your WSL Ubuntu
terminal**, not PowerShell.

### 1. WSL2 + Ubuntu

If you don't already have a distro installed:

```powershell
wsl --install -d Ubuntu-22.04
```

Reboot if prompted, then open the "Ubuntu" app from the Start menu to
finish first-run account setup. Everything from here on runs inside
that Ubuntu shell.

### 2. System packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git zip unzip \
    openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev \
    libncurses-dev cmake libffi-dev libssl-dev build-essential
```

Confirm Java resolved to 17 (buildozer/p4a is picky about this):

```bash
java -version
```

### 3. Project virtualenv + buildozer

From the project root inside WSL (if your project lives under
`/mnt/c/...`, `cd` there; a native WSL filesystem path like
`~/notenest` builds noticeably faster than `/mnt/c/...`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install buildozer cython==0.29.36
```

### 4. First build

```bash
buildozer -v android debug
```

The **first** run downloads and installs the Android SDK, build-tools,
and the NDK version pinned in `buildozer.spec` (`android.ndk`,
`android.api`, `android.build_tools`) into `~/.buildozer/` — this can
take 20-40 minutes and several GB depending on connection speed.
Subsequent builds reuse that cache and are much faster. The resulting
APK lands in `bin/`.

Do **not** hand-install a different SDK/NDK version and point
`ANDROID_HOME`/`ANDROID_SDK_ROOT` at it — let buildozer manage its own
copy per the versions pinned in `buildozer.spec`, so every teammate's
build environment matches.

### Keeping versions in sync

`buildozer.spec`'s `requirements =` line and the repo-root
`requirements.txt` pin the exact same Kivy/KivyMD/etc. versions and
must be updated together — see the comments in `requirements.txt` for
why KivyMD is pinned to a specific git commit instead of a normal
version number, and how to bump it.
