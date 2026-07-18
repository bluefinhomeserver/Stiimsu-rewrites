# Manual Waydroid Installation on SteamOS — The Complete Guide

Run Android natively inside SteamOS on the Steam Deck — no dual-booting, no virtual machines, no third-party install scripts. This guide documents a fully manual Waydroid installation, including every pitfall, failure mode, and fix discovered along the way.

> **Why manual?** The community installer script ([steamos-waydroid-installer](https://github.com/ryanrudolfoba/steamos-waydroid-installer)) is excellent and is the right choice for most people. Go manual if: the script doesn't support your SteamOS/kernel version (e.g. experimental/preview builds), you want to understand and control exactly what touches your system, or the script is broken for your setup. This guide was developed on an experimental kernel the script refused to support.

> **Tested environment:** SteamOS (main/preview channel), kernel `6.16.x-neptune` (drm-exec branch), glibc 2.41, Python 3.13, Waydroid 1.6.3, Android 13 (LineageOS 20 vanilla image). Your versions will differ — the *methods* here (especially the compatibility-diagnosis techniques) transfer; the exact package versions may not.

---

## Table of Contents

1. [How It Works](#1-how-it-works)
2. [Prerequisites](#2-prerequisites)
3. [Step 1 — Unlock the System](#3-step-1--unlock-the-system)
4. [Step 2 — Check Binder Support](#4-step-2--check-binder-support)
5. [Step 3 — Install Waydroid Packages (the ABI gauntlet)](#5-step-3--install-waydroid-packages-the-abi-gauntlet)
6. [Step 4 — Relocate Storage Before Init](#6-step-4--relocate-storage-before-init)
7. [Step 5 — Initialize Android (download pitfalls)](#7-step-5--initialize-android-download-pitfalls)
8. [Step 6 — Fix Networking (firewalld)](#8-step-6--fix-networking-firewalld)
9. [Step 7 — First Launch](#9-step-7--first-launch)
10. [Step 8 — Housekeeping & Update Survival](#10-step-8--housekeeping--update-survival)
11. [Optional Extras](#11-optional-extras)
12. [Deep Troubleshooting Reference](#12-deep-troubleshooting-reference)

---

## 1. How It Works

Waydroid is **not an emulator**. It runs a full Android system in an LXC container that shares the host Linux kernel, so Android apps run at near-native speed. On SteamOS this requires:

- **Binder** — Android's IPC driver — available in the kernel (built-in or as a module)
- The **waydroid** package and its dependency chain (lxc, dnsmasq, python-gbinder → libgbinder → libglibutil)
- Android **system and vendor images** (LineageOS-based, downloaded by `waydroid init`)
- Working **bridge networking** between container and host

None of these ship with SteamOS, and SteamOS's package snapshot lags Arch Linux — which creates the central challenge of this guide: **ABI version drift**. Current Arch packages are built against newer glibc/Python than SteamOS carries. The recurring solution: *never upgrade core system libraries to satisfy an app; always downgrade the app to match the system*, using the [Arch Linux Archive](https://archive.archlinux.org/packages/).

---

## 2. Prerequisites

- Steam Deck in **Desktop Mode** (Steam button → Power → Switch to Desktop)
- A **sudo password** set: open Konsole, run `passwd`
- ~4 GB free space on `/home` (images + app data)
- Stable Wi-Fi — and read the Wi-Fi powersave warning in Step 5 *before* downloading anything
- Comfort with a terminal; nothing here is hard, but you'll be reading error messages

**Set up your workspace:**

```bash
mkdir -p ~/waydroid-pkgs
```

This folder becomes your **survival kit** — keep every working package file in it forever (see Step 8).

---

## 3. Step 1 — Unlock the System

SteamOS's root filesystem is immutable (read-only) by default, and pacman's keyring starts uninitialized.

```bash
sudo steamos-readonly disable
sudo pacman-key --init
sudo pacman-key --populate archlinux holo
```

> **Remember to re-enable readonly at the end** (Step 8). Everything you install remains after re-locking; the lock only prevents *new* modifications.

---

## 4. Step 2 — Check Binder Support

This determines whether you face the easiest or hardest version of this install. Check before doing anything else:

```bash
zgrep -i binder /proc/config.gz
```

**Outcome A — `CONFIG_ANDROID_BINDER_IPC=y` (built into the kernel):** You're done with this step. Nothing to install, and — bonus — binder support survives all future SteamOS updates. Newer SteamOS kernels increasingly ship this. Note that `modprobe binder_linux` will say "module not found" in this case — that's *correct*, there is no module because it's compiled in. Optionally confirm binderfs works:

```bash
sudo mkdir -p /dev/binderfs
sudo mount -t binder binder /dev/binderfs
ls /dev/binderfs        # should show binder-control
```

(Waydroid's service does this mount itself at startup; the manual mount is just a test.)

**Outcome B — `=m` or absent:** You need a binder module built for your *exact* kernel (`uname -r`). Options, in order of preference:

1. **Borrow a prebuilt module** from the [community installer repo](https://github.com/ryanrudolfoba/steamos-waydroid-installer) — it ships `binder_linux.ko` files per SteamOS kernel. Find one matching your `uname -r`, then:
   ```bash
   sudo mkdir -p /lib/modules/$(uname -r)/updates
   sudo cp binder_linux.ko* /lib/modules/$(uname -r)/updates/
   sudo depmod -a && sudo modprobe binder_linux
   echo binder_linux | sudo tee /etc/modules-load.d/waydroid.conf
   ```
2. **Build via DKMS**: install `base-devel`, `dkms`, and the `linux-neptune-*-headers` package *exactly matching* your running kernel, then build `binder_linux-dkms` from the AUR with `makepkg -si` (as the deck user, never root). If no headers package matches your exact kernel string, stop — a module built against mismatched headers will not load.

> **Pitfall:** In Outcome B, the module lives on the root filesystem and is **wiped by SteamOS updates**. Keep the `.ko` file in your survival kit.

---

## 5. Step 3 — Install Waydroid Packages (the ABI gauntlet)

Waydroid is not in Valve's repos (verify: `sudo pacman -Syy && pacman -Ss waydroid`). We install Arch Linux's official packages directly with `pacman -U`.

**Golden rules for this entire step:**
- Never run `pacman -Syu`. Never let pacman upgrade `glibc`, `python`, `systemd`, or other core packages — if it proposes that, **abort**. Breaking these can brick the OS.
- Prefer Valve's repo when it has a package (`pacman -Ss <name>` → `pacman -S <name>`) — Valve builds are guaranteed ABI-compatible.
- Verify every downloaded file before installing: `pacman -Qip file.pkg.tar.zst` shows its real name/version; `file *.pkg.tar.zst` should say "Zstandard compressed data" (an HTML error page in disguise is a classic failure).

### 3a. Download the packages

```bash
cd ~/waydroid-pkgs
curl -L -o waydroid.pkg.tar.zst        https://archlinux.org/packages/extra/any/waydroid/download/
curl -L -o python-gbinder.pkg.tar.zst  https://archlinux.org/packages/extra/x86_64/python-gbinder/download/
curl -L -o libgbinder.pkg.tar.zst      https://archlinux.org/packages/extra/x86_64/libgbinder/download/
curl -L -o libglibutil.pkg.tar.zst     https://archlinux.org/packages/extra/x86_64/libglibutil/download/
curl -L -o lxc.pkg.tar.zst             https://archlinux.org/packages/extra/x86_64/lxc/download/
```

> **Pitfalls encountered here:**
> - **waydroid is an `any` package**, not `x86_64` (it's pure Python) — the x86_64 URL 404s and you get an HTML page saved as a .zst. If `pacman -Qip` says "Unrecognized archive format", you downloaded an error page.
> - Always use `curl -L -o <name>` (explicit output name). `curl -JLO` fails silently on repeat downloads (refuses to overwrite) or overwrites the same `download` file repeatedly — both happened during development and produced duplicate/mislabeled files. **Verify with `pacman -Qip` that each file's internal Name matches its filename.**

### 3b. dnsmasq — try Valve's repo first

```bash
pacman -Ss dnsmasq
```

If found: `sudo pacman -S dnsmasq` and skip Arch's dnsmasq entirely (current Arch's build wants a newer nettle library than SteamOS ships — the error looks like `cannot resolve "libnettle.so=9-64"`). If Valve's repo lacks it, fetch an older build from the archive (see 3d for the technique).

### 3c. Install and read pacman's verdict

```bash
sudo pacman -U ./*.pkg.tar.zst
```

- **Missing dependency X** → find X on archlinux.org/packages (note whether it's `extra`/`core` and `x86_64`/`any` — the URL differs), download, re-run.
- **Wants to upgrade glibc/python/systemd** → abort. Full stop.
- Wall of "Conflict with earlier configuration for user/group … ignoring line" during hooks → **harmless SteamOS noise** (Valve pins UIDs/GIDs); ignore.

### 3d. The compatibility test — and how to fix failures

```bash
waydroid --version
```

A clean version number = done. The two failures seen in practice, and the general fix pattern:

**Failure 1 — `ModuleNotFoundError: No module named 'gbinder'`.** Arch's python-gbinder was compiled for a newer Python than SteamOS runs. Diagnose:

```bash
python3 --version                                      # e.g. 3.13.x
ls -d /usr/lib/python3.*/site-packages/gbinder*        # e.g. installed under python3.14 ← mismatch
```

Fix: get the last python-gbinder built for *your* Python from the [Arch Archive](https://archive.archlinux.org/packages/p/python-gbinder/). Verify a candidate *before* installing:

```bash
pacman -Qlp candidate.pkg.tar.zst | grep site-packages | head -3
# paths must show YOUR python3.X; the .so must be tagged cpython-<yourversion>
sudo pacman -U candidate.pkg.tar.zst      # confirm the downgrade prompt
```

**Failure 2 — `lxc-info: /usr/lib/libc.so.6: version 'GLIBC_2.4x' not found`.** Arch's lxc wants newer glibc. Check yours (`ldd --version | head -1`), then browse [archive.archlinux.org/packages/l/lxc/](https://archive.archlinux.org/packages/l/lxc/) and pick a build **dated from the era your glibc was current** in Arch (glibc 2.41 ≈ first half of 2025 → lxc 6.0.x builds). URL note: lxc versions contain an epoch colon that must be encoded, e.g. `lxc-1%3A6.0.4-1-x86_64.pkg.tar.zst`. Install, then the empirical gate:

```bash
lxc-info --version    # bare version number = correct vintage; GLIBC error = step one build older, repeat
```

Iterating is cheap (~1 MB per attempt). Waydroid works fine with lxc 5/6/7 alike.

> **The general pattern for ANY such failure:** identify the incompatible package from the error → find its historical builds in the Arch Archive → pick one from the period matching your system's glibc/Python era → verify with `pacman -Qlp`/`-Qip` → `pacman -U` → retest. Keep the working file in your survival kit.

---

## 6. Step 4 — Relocate Storage Before Init

**Do this BEFORE `waydroid init` or init will fail with `[Errno 28] No space left on device`** — even on a brand-new Deck. SteamOS's root/`/var` partitions are only a few GB and mostly full *by design*; all your real space is on `/home`. Waydroid defaults to `/var/lib/waydroid` for its ~3 GB of images.

```bash
mkdir -p /home/deck/waydroid/var
sudo ln -s /home/deck/waydroid/var /var/lib/waydroid
```

(User app data goes to `~/.local/share/waydroid`, already on /home — no action needed.)

**If init already failed with the space error:** `sudo rm -rf /var/lib/waydroid`, then create the symlink, then re-init.

**SD card variant:** same technique, pointed at a SteamOS-formatted (ext4) card mount instead — but the card must then always be inserted before starting Waydroid, and FAT/exFAT cards won't work (Android needs Linux permissions). Installing to /home first and migrating later is painless: stop everything, `mv` the directory, re-point the symlink.

---

## 7. Step 5 — Initialize Android (download pitfalls)

**FIRST — disable Wi-Fi power saving.** The Deck's Wi-Fi powersave aggressively naps the radio and **corrupts/kills long downloads** (symptoms: throughput collapsing from 8 MB/s to 200 kB/s, `SSL_read: unexpected eof`, repeated hash-validation failures). Make the fix permanent while the filesystem is unlocked:

```bash
sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf > /dev/null << 'EOF'
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager
```

Then initialize. For vanilla Android (no Google services):

```bash
sudo waydroid init
```

For Google apps included: `sudo waydroid init -s GAPPS` (note: Play Store sign-in later requires registering the device at google.com/android/uncertified — the Waydroid Toolbox or `waydroid shell -- sh -c "settings get secure android_id"` gets you the ID).

This downloads a ~840 MB system image + ~190 MB vendor image from SourceForge and validates their SHA-256 hashes.

### Critical pitfalls in this step

**The `-f` flag trap.** `-f` means *force re-download, ignore cache*. Use it at most once, at the very beginning, and **never on retries** — otherwise every retry throws away previously downloaded (even fully valid, cached) data and starts over. If you have a valid cached image, plain `sudo waydroid init` uses it; `init -f` deletes your progress. This single flag caused hours of repeated downloads during development.

**`init` needs root.** `Action "init" needs root access` = you forgot `sudo`. (Session/UI commands later must run *without* sudo — root modifies the system, your user runs the session.)

**Hash mismatch / dropped downloads.** SourceForge redirects to random mirrors of wildly varying quality, and init's downloader can't resume. If downloads keep dying, take manual control:

```bash
# Waydroid caches downloads in cache_http, named by the MD5 of the source URL.
# If a partial file exists there, its filename is already the correct cache name — reuse it.
cd /var/lib/waydroid/cache_http && ls -la

# Download with RESUME support from SourceForge's master mirror (slower, reliable):
sudo curl -L -C - -o <cache-filename> \
  'https://master.dl.sourceforge.net/project/waydroid/images/system/lineage/waydroid_x86_64/<image-filename>?viasf=1'
# Re-run the same command after any drop — it resumes, never loses progress.

# THE GATE — verify before involving init (expected hash is printed in init's error message):
sha256sum <cache-filename>

# Only when the hash matches:
sudo waydroid init        # no -f! It validates the cache instantly and moves on.
```

If starting fresh with no cache file: the cache filename = `echo -n '<exact-URL-init-prints>' | md5sum` (the URL ends in `/download`; `-n` matters). The same technique applies to the vendor image if it also misbehaves.

**Success looks like:** `Validating system image` → `Extracting to /var/lib/waydroid/images` → same for vendor → init returns with no ERROR. A final error mentioning `lxc-info --version` at this point is the glibc/lxc issue from Step 3d — fix it and re-run plain `init`; images won't re-download.

---

## 8. Step 6 — Fix Networking (firewalld)

**Do this proactively — on a default SteamOS, Android will boot with no internet otherwise, and the failure is silent and deeply confusing.**

The cause: SteamOS runs **firewalld**. The `waydroid0` bridge belongs to no firewall zone, so it lands in the restrictive default zone, and Android's DHCP requests (and DNS queries) are **silently dropped** on the host. Android's DHCP client broadcasts forever; dnsmasq never hears it; Android ends up with only an IPv6 link-local address. Plain iptables ACCEPT rules do **not** fix this — firewalld's nftables hooks filter independently of the legacy iptables table.

The canonical two-line fix:

```bash
sudo firewall-cmd --zone=trusted --add-interface=waydroid0
sudo firewall-cmd --zone=trusted --add-interface=waydroid0 --permanent
```

Plus NAT forwarding, made persistent (a `sysctl -w` alone does not survive reboots):

```bash
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-waydroid.conf
sudo sysctl -w net.ipv4.ip_forward=1
```

With both in place, Android DHCPs natively on boot — address, routes, and DNS all configure themselves, and no other network workaround is needed. (If you're curious or debugging: the full diagnostic journey is in the [troubleshooting reference](#12-deep-troubleshooting-reference).)

---

## 9. Step 7 — First Launch

```bash
sudo systemctl enable --now waydroid-container
waydroid session start &
# WAIT for "Android with user 0 is ready" in the output (30–60s on first boot), then:
waydroid show-full-ui
```

Notes:

- **Session/UI commands run as your user, not root.**
- On the **Plasma Wayland** desktop session, the UI opens as a native window. On an **X11** session you need the `cage` compositor as a wrapper: `cage -- waydroid show-full-ui`. (cage also isn't in Valve's repos — same `pacman -U` treatment, and it drags a specific wlroots version; only bother if you're actually on X11: check with `echo $XDG_SESSION_TYPE`.)
- **"Session is already running" + "Failed to access IPlatform service"** → a stale session from earlier attempts. Clean restart: `waydroid session stop && sudo systemctl restart waydroid-container && waydroid session start &`, wait for ready, then `show-full-ui`. Baking this stop/restart/wait sequence into a launcher script makes launches slower but always clean.
- First boot shows a black screen / boot animation for a minute or two. Subsequent boots are faster.

**A convenient launcher (`~/android.sh`, `chmod +x`, add as a Non-Steam game):**

```bash
#!/bin/bash
waydroid session stop
sudo systemctl restart waydroid-container
waydroid session start &
sleep 20
waydroid show-full-ui
```

(For Gaming Mode use, the embedded sudo needs a passwordless sudoers rule for that one systemctl command, or drop the restart lines and accept occasional stale-session cleanup by hand.)

---

## 10. Step 8 — Housekeeping & Update Survival

**Re-lock the filesystem:**

```bash
sudo steamos-readonly enable
```

**The survival kit.** SteamOS updates **wipe everything installed on the root filesystem** — all the pacman packages (and any binder module) — but your Android images, apps, and data survive (they live on /home via the symlink), as does the firewalld rule and the sysctl/NetworkManager config files in `/etc`. Recovery after an OS update:

```bash
sudo steamos-readonly disable
sudo pacman-key --init && sudo pacman-key --populate archlinux holo
sudo pacman -U ~/waydroid-pkgs/*.pkg.tar.zst
sudo pacman -S dnsmasq                      # if it came from Valve's repo
# re-create the /var/lib/waydroid symlink if the update removed it:
ls -la /var/lib/waydroid || sudo ln -s /home/deck/waydroid/var /var/lib/waydroid
sudo steamos-readonly enable
```

Five minutes, no re-downloads, no re-init. **This only works if you kept every working .pkg.tar.zst** — the Arch Archive's "latest" moves on, but your stashed files are frozen at known-compatible versions. Add a NOTES.txt recording your kernel, glibc, and Python versions and which package vintages matched them.

**Daily-driver commands:**

```bash
waydroid session stop                     # shut Android down cleanly
sudo systemctl stop waydroid-container    # fully off, frees RAM
waydroid app install ~/Downloads/app.apk  # sideload an APK
waydroid app list
sudo waydroid shell                       # root shell inside Android
sudo waydroid shell -- logcat -d          # Android logs (note: -d works INSIDE the
                                          # shell; 'waydroid logcat -d' does not parse)
```

---

## 11. Optional Extras

**ARM translation (libndk).** The Deck is x86_64; most Android apps ship ARM-only. Pure-Java/Kotlin apps run fine without translation, but for broad APK compatibility install libndk via [casualsnek/waydroid_script](https://github.com/casualsnek/waydroid_script):

```bash
git clone https://github.com/casualsnek/waydroid_script && cd waydroid_script
python3 -m venv venv && venv/bin/pip install -r requirements.txt
sudo venv/bin/python3 main.py     # choose libndk (and widevine for DRM apps if wanted)
sudo systemctl restart waydroid-container
```

Prefer x86_64 APK builds when sites offer them (APKMirror labels architectures) — they skip translation entirely.

**App sources without Google:** sideload F-Droid (open-source apps) and/or Aurora Store (anonymous Play catalogue frontend), then install everything from inside Android.

**Controller support:** launch Waydroid through Steam (Non-Steam shortcut) with the layout set to plain **Gamepad** — Steam Input then presents a standard virtual controller that passes through to Android. Test with a gamepad-tester app inside Android. If Android sees nothing, it's usually input-device permissions (`/dev/input/event*` readability) — a udev rule granting read access fixes it persistently. For touch-only games, Mantis Gamepad Pro + Shizuku inside Android maps physical controls onto touch overlays.

---

## 12. Deep Troubleshooting Reference

**"No space left on device" during init** → Step 4. `/var` is tiny by design; symlink to /home.

**Hash mismatch loops during init** → Step 5. Check for `-f` on retries (the #1 cause), then Wi-Fi powersave, then manual master-mirror download with sha256 verification.

**`ModuleNotFoundError` on any waydroid Python import** → wrong-Python-version package; Step 3d technique.

**`GLIBC_2.xx not found` from any binary** → newer-than-system build; Step 3d technique (archive downgrade of *that app*, never of glibc).

**Android boots but no internet** — layered diagnosis, container-outward:

```bash
sudo waydroid shell -- ip addr show eth0            # has an IPv4 address?
sudo waydroid shell -- ping -c 2 192.168.240.1      # container → host bridge
sudo waydroid shell -- ping -c 2 1.1.1.1            # container → internet (NAT path)
sudo waydroid shell -- ping -c 2 google.com         # DNS
```

- **No IPv4 on eth0** = DHCP failing. Check dnsmasq is running and bound to waydroid0 (`ps aux | grep dnsmasq`), then watch `sudo journalctl -u waydroid-container -f` while restarting the session: if you see **zero DHCPDISCOVER lines** while Android's logcat shows `DhcpClient: Broadcasting DHCPDISCOVER`, packets are being dropped on the host → **firewalld zone fix (Step 6)** — this is the classic case. A successful lease shows DISCOVER→OFFER→REQUEST→ACK in the journal.
- **Bridge pings, internet doesn't** → check `cat /proc/sys/net/ipv4/ip_forward` is 1 (Step 6 persistence) and that a MASQUERADE rule exists (`sudo iptables -t nat -L POSTROUTING -n -v`).
- **IPs work, names don't** → DNS; with the firewalld fix in place DHCP delivers DNS automatically, so this usually means the fix is missing or the lease predates it — restart the session.
- **Manually-set routes "unreachable" despite existing**: Android uses **policy routing** — netd builds per-network tables (`ip rule show` reveals them, ending in `from all unreachable`) and **never consults the main routing table**. Manual routes must go into the interface's own table: `ip route replace default via 192.168.240.1 dev eth0 table eth0`. You should never need this with working DHCP, but it's the key to any manual network surgery inside the container.

**Session starts but UI never appears / IPlatform errors** → stale session; clean-restart sequence in Step 7.

**`waydroid logcat -d` errors with "unrecognized arguments"** → the wrapper doesn't pass flags through; run logcat inside the shell: `sudo waydroid shell -- logcat -d`.

**Everything broke after a SteamOS update** → expected; Step 8 recovery procedure.

---

## Credits & Further Reading

- [Waydroid](https://waydro.id/) — the project itself
- [ryanrudolfoba/steamos-waydroid-installer](https://github.com/ryanrudolfoba/steamos-waydroid-installer) — the community script; its source is an excellent reference for what a working SteamOS setup requires, and its prebuilt binder modules are useful even for manual installs
- [casualsnek/waydroid_script](https://github.com/casualsnek/waydroid_script) — ARM translation, Widevine, and other image extras
- [Arch Linux Archive](https://archive.archlinux.org/packages/) — historical package builds, the key to every ABI-drift fix in this guide

*This guide was written after (and because of) one very long night of doing everything the hard way, so that yours can be a short evening instead.*
