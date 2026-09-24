<img width="3840" height="1280" alt="Image" src="https://github.com/user-attachments/assets/0f275ad2-94a3-4ed5-aa82-de3ec7409f24" />

# Stiimsu
A SteamOS-Android bridge for running iisu and playing through linux-native emulators.

# iisu-bridge — Full Setup Guide (Linux)

[Original Steamguide here](https://github.com/bluefinhomeserver/Stiimsu-rewrites/blob/main/iiSU%20SteamOS.md)

Run the **iiSU** Gaming frontend on your Linux Operating System, but have every game
launch a **Linux native emulator** e.g PCSX2, Dolphin, RPCS3, RetroArch etc 
instead of inside waydroid/android emulation.

How it works: 
- iiSU runs inside **Waydroid** (an Android
container).
- When you press play, a tiny **stub APK** impersonating the Android
emulator catches the launch, and sends the game's path to a small **daemon**
on the Linux side, which translates the path and starts your native
emulator.
- A control-panel web app, **Stiimsu Helper**, manages all of it.

> Note:
> Please use your own legally obtained games and BIOS files, dumped
> from hardware you own. This project only launches emulators and hands them
> files you already have.

**What's in the project zip**

```
stiimsu-helper/
  README.md                  this guide
  stiimsu_helper.py          the Stiimsu Helper app (backend + UI)
  run-stiimsu-helper.sh      launcher for the app
  install.sh                 installer (app + daemon + menu entry)
  iisu_bridge_daemon.py      the bridge daemon
  tools/ps3dec               optional PS3 ISO decrypter (see PS3 section)
  data/
    consoles.json            console list + iiSU identities
    emulators.default.json   default host commands
    apks/                    20 pre-built stub APKs
```

Supported consoles: 
* PS1
* PS2
* PS3
* PSP
* GameCube
* Wii
* Wii U
* N64
* SNES
* Game Boy / Color / Advance
* DS
* 3DS
* Mega Drive
* Sega CD
* Saturn
* Dreamcast
* Atari 2600
* Atari Jaguar
* Xbox
* Xbox 360
* RetroArch as a multi-system emulator

---

## 1. Install Waydroid

Waydroid is the Android container that hosts iiSU.

You can install Waydroid from your package manager.

for example

Arch based:

```bash
pacman -S Waydroid

paru -S Waydroid
```
etc.

Ubuntu/Debian:
```bash
sudo apt install Waydroid
```
etc.

However you can also build Waydroid yourself which may be reccomended. Please read **WAYDROID-STEAMOS-GUIDE.md** to learn how to do that yourself.

Sanity check when done:

```bash
waydroid status        # should say the session is RUNNING while Waydroid is open
ls ~/.local/share/waydroid/data/media/0/    # Android's /sdcard, on the host side
```

## 2. Install iiSU into Waydroid

Get the iiSU APK from the iiSU project, then (with the Waydroid session
running):

```bash
waydroid app install ~/Downloads/iiSU_*.apk
```
You can alternatively install it within the Waydroid emulator by navigating online. 

Give iiSU full storage access so it can see your game library:

```bash
sudo waydroid shell -- appops set com.iisulauncher MANAGE_EXTERNAL_STORAGE allow
```

Open iiSU once from Waydroid to confirm it runs.

Waydroid Fulscreen KDE

Waydroid Fulscreen

```bash
waydroid prop set persist.waydroid.width <Monitor_width> waydroid prop set persist.waydroid.height <Monitor_height> waydroid session stop #relaunch waydroid
sudo waydroid shell wm size #shows current waydroid size
```

## 3. Create the ROM library (one-time)

Games live inside Waydroid's shared storage so both worlds can see them:
`~/.local/share/waydroid/data/media/0/roms/<console>/`. That tree is
root-owned by Android, so hand yourself the `roms` part once:

```bash
sudo mkdir -p ~/.local/share/waydroid/data/media/0/roms
sudo chown -R <user>:<user> ~/.local/share/waydroid/data/media/0/roms
sudo chmod a+rX ~/.local/share/waydroid/data/media/0/roms
```

(REPLACE `<user>` with your linux user)

After this, the Stiimsu Helper's **Add a game** screen can create per-console
subfolders and copies files for you into the`/roms` folder.

## 4. Allow the bridge its two privileged actions

The daemon needs passwordless rights for exactly two things:
- Driving Waydroid (stop/relaunch iiSU during game boot and close)
- Re-opening the traversal permission Android relocks on the media folders at every boot.

The commands run in this step create the sudoers file with the the `zz-` prefix matters (sudoers files are read alphabetically and the last
match wins, so this must sort after SteamOS's own files):

Bash (works on most normal setups) :

```bash
sudo tee /etc/sudoers.d/zz-iisu-bridge > /dev/null << 'EOF'
<user> ALL=(root) NOPASSWD: /usr/bin/waydroid
<user> ALL=(root) NOPASSWD: /usr/bin/chmod o+x /home/<user>/.local/share/waydroid/data
<user> ALL=(root) NOPASSWD: /usr/bin/chmod o+x /home/<user>/.local/share/waydroid/data/media
<user> ALL=(root) NOPASSWD: /usr/bin/chmod o+x /home/<user>/.local/share/waydroid/data/media/0
EOF
sudo chmod 440 /etc/sudoers.d/zz-iisu-bridge
```

Rewritten for fish shell (CachyOS etc.):

```bash
echo "<user> ALL=(root) NOPASSWD: /usr/bin/waydroid  
<user> ALL=(root) NOPASSWD: /usr/bin/chmod o+x /home/<user>/.local/share/waydroid/data  
<user> ALL=(root) NOPASSWD: /usr/bin/chmod o+x /home/<user>/.local/share/waydroid/data/media  
<user> ALL=(root) NOPASSWD: /usr/bin/chmod o+x /home/<user>/.local/share/waydroid/data/media/0" | sudo tee /etc/sudoers.d/zz-iisu-bridge > /dev/null

sudo chmod 440 /etc/sudoers.d/zz-iisu-bridge
```


(REPLACE `<user>` with your linux user)

## 5. Install the bridge and the Helper

Unzip this bundle and run the installer (first extract the stiimsu-helper folder into a directory of your choice then cd into that):

```bash
cd ~/<directory>/stiimsu-helper
chmod +x install.sh
./install.sh
```

(REPLACE `<directory>` with your linux directory)

This copies the app to `~/Documents/iisu-bridge/app/`, deploys the daemon to
`~/Documents/iisu-bridge/iisu_bridge_daemon.py`, seeds
`~/Documents/iisu-bridge/emulators.json` with defaults (kept and merged on
future re-runs, never overwritten), and adds **Stiimsu Helper** to your app
menu. Re-running `install.sh` is also how you update later.

## 6. Create the daemon service

The daemon runs as a systemd *user* service, started on demand by the
launcher (it does not auto-start at boot)

Bash (works on most normal setups) :

```bash
mkdir -p ~/.config/systemd/user
tee ~/.config/systemd/user/iisu-bridge.service > /dev/null << 'EOF'
[Unit]
Description=iiSU bridge daemon (Waydroid frontend -> native SteamOS emulators)

[Service]
ExecStart=/usr/bin/python3 /home/<user>/Documents/iisu-bridge/iisu_bridge_daemon.py
Restart=on-failure
EOF
systemctl --user daemon-reload
```

Rewritten for fish shell(CachyOS etc.):

```bash
mkdir -p ~/.config/systemd/user  
echo "[Unit]  
Description=iiSU bridge daemon (Waydroid frontend -> native SteamOS emulators)

[Service]  
ExecStart=/usr/bin/python3 /home/<user>/Documents/iisu-bridge/iisu_bridge_daemon.py  
Restart=on-failure" | sudo tee ~/.config/systemd/user/iisu-bridge.service > /dev/null

systemctl --user daemon-reload

```

(REPLACE `<user>` with your linux user)

## 7. Launch iiSU

iiSU helper and iiSU for steam OS should have appeared under Games in the desktop menu. You can add a shortcut to desktop if it is missing.

In the Steam desktop app → Games → Add a Non-Steam Game
to My Library → pick iiSU Frontend. 

You can also add custom artwork to the steam shortcut via the custom artwork folder.

## 8. Install your emulators

The bridge launches whatever you have; it doesn't ship emulators.

Flatpaks (from Discover) work out of the box for most systems — DuckStation,
Dolphin, PPSSPP, Flycast, RPCS3, Cemu, Azahar, mGBA, DeSmuME, Stella, xemu.
The Helper knows their default launch commands.

AppImages should go in `~/Applications/`, made executable, ideally with a
version-proof symlink you point commands at:

```bash
chmod +x ~/Applications/(YourEmu)-(version).AppImage
ln -sf ~/Applications/(YourEmu)-(version).AppImage ~/Applications/youremu-stable
```

The Helper auto-detects AppImages here: if a console's default flatpak isn't
installed but a matching AppImage exists, the default command adapts to it.
For RetroArch, download the cores you want inside RetroArch itself (Online
Updater → Core Downloader); if you use the AppImage build, symlink its
portable cores folder to the standard location so the bridge finds them:

```bash
mkdir -p ~/.config/retroarch
ln -s ~/Applications/RetroArch-*/RetroArch-*.AppImage.home/.config/retroarch/cores \
      ~/.config/retroarch/cores 2>/dev/null || true
```

Two Windows-only emulators need a `wine`/Proton wrapper you configure
yourself via Custom command: **Xenia** (Xbox 360) and **BigPEmu** (Jaguar —
or use the RetroArch VirtualJaguar default instead), I won't go over the exact details here.

## 9. Using Stiimsu Helper

Launch **Stiimsu Helper** from the app menu (Waydroid should be running when
installing stubs). It opens in your browser, quits itself when you close the
tab, and shows its version in the footer. It has 3 menu options:

**Set up an emulator.** Pick a console. The info box shows which Android
package iiSU will be tricked into seeing. Keep the **Default** command, or
switch to **Custom** and Browse to your emulator (keep `{rom}` where the game
path goes). A live checkmark under the command tells you whether the
executable actually exists *before* you save. RetroArch-based commands get a
**core picker** listing your installed cores. If the command is a flatpak, a
checkbox offers to grant it access to the Waydroid folder — leave it ticked;
sandboxed flatpaks otherwise open and claim the file doesn't exist. Click
**Install stub & save emulator**: the command saves instantly (the daemon
picks it up with no restart) and the stub APK installs into Waydroid.

**Add a game.** Pick the console, Browse to your ROM/ISO, click Add. The file
is copied into the library and made readable. **PS3 is special** — see below.

**Importing all your already existing roms**

If you have a folder already containing roms, structured correctly

*structure.png*


You can import your entire collection into iisu by binding the folders.
This does not add extra storage.
Binding as similar to symlinks in the sense that it routes to the destination

```bash
sudo mount --bind ~/.local/share/waydroid/data/media/0/ /<filepath>
```
(REPLACE <filepath> with your filepath)
(if you have spaces in your file path, add brackets, like this "/<filepath>")

**Manage library.** Lists everything in the roms tree with sizes (PS3
marker+folder pairs shown as one game) and deletes cleanly, including the
read-only folders disc extraction produces. This is the supported way to
delete games as doing it from inside Waydroid does not work.

### PS3 games

RPCS3 cannot play ISO files, it needs the disc *extracted*. The Helper does
this automatically: pick a PS3 ISO in **Add a game** and it's extracted into
`roms/ps3/Game.ps3.dir/`, with a small `Game.ps3` marker file written beside
it — the marker is what iiSU shows as the game, and the daemon redirects it
to the real boot file at launch.

Note: If you see an error like 7z failed and/or bsdtar: failed when trying to add a game to your library,
this can normally be ignored and the game will be added sucessfully.

Note 2: the ISO must be a **decrypted** dump. PC-made (redump-style) ISOs
are encrypted and come with a `.dkey` file holding the disc key. Decrypt
first with the bundled static `ps3dec` (no dependencies, runs on stock
SteamOS), or decrypt it using another ps3 decryption application:

```bash
chmod +x ~/Downloads/stiimsu-helper/tools/ps3dec
~/Downloads/stiimsu-helper/tools/ps3dec d key <32-hex-key-from-the-.dkey-file> \
    encrypted.iso decrypted.iso
```

Then add the `decrypted.iso` through the Helper. Also the first time — RPCS3
needs its firmware installed (`PS3UPDAT.PUP` via File → Install Firmware).

## 10. Configure iiSU and play

Inside iiSU, for each console: add the library folder, point its folder
picker at `roms/<console>` under internal storage and assign the emulator
matching the stub you installed (e.g. AetherSX2 for PS2, DuckStation for PS1, 
RetroArch for anything you have the core installed on. Then press play: iiSU
launches the stub, the stub calls the daemon, your native emulator opens over
Waydroid, and iiSU quietly closes during play and returns when you exit the
game.

## 11. Updating

Download the new bundle, then:

```bash
pkill -f stiimsu_helper
cd ~/<directory> && rm -rf stiimsu-helper && unzip stiimsu-helper.zip
cd stiimsu-helper && ./install.sh
```
(REPLACE <directory> with your linux directory)

## 12. Troubleshooting

To see debugging logs for any errors that could appear: `journalctl --user -u iisu-bridge -f`

Common issues:

*Emulator opens but "file not found"* — a flatpak sandbox problem. Re-run the
emulator setup with the sandbox checkbox ticked, or manually:
`flatpak override --user <app-id> --filesystem=~/.local/share/waydroid`.

*Toast says "emulator executable not found"* — the saved command points at a
moved/deleted binary (this is why the stable-symlink convention exists). Open
the console in the Helper; the checkmark line names the problem.

*"rom not found"* — the journal's `[reject]` line prints the exact android
path, host path, and whether it exists; the answer is in it.

*Game added but not in iiSU* — Android's stale media index; restart the
Waydroid session and re-add/rescan in iiSU.

*"emulator already running" (409)* — a previous game is still open; the
bridge runs one at a time.

*RetroArch launches nothing* — the core isn't installed in the host
RetroArch, or the command points at a RetroArch you don't have (flatpak vs
AppImage). The core picker and checkmark line in the Helper resolve both.

*iiSU shows a stale error from a previous attempt* — iiSU sometimes redisplays
the last emulator error; check the journal timestamps

## 13. Security note

All stubs, the daemon, and the launcher share one bridge token, baked in at
build time. The daemon only listens on the Waydroid-internal interface
(`192.168.240.1`), never on your network, and only ever runs whitelisted
emulator commands against validated paths so exposure is limited to apps
running inside your own Waydroid container. Don't change the daemon's bind
address to `0.0.0.0`.
