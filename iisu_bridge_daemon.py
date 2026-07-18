

import json
import shlex
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BIND_ADDR = "192.168.240.1"
BIND_PORT = 5987
TOKEN = "1WIHHnI7SLKgQKuw5Akg5q3oehBy6lsXSsy7FN3DnSi6nOjhTnF_apgdb-eZBdu-"
_TOKEN_FILE = Path.home() / "Documents/iisu-bridge/token"


def get_token() -> str:
    try:
        t = _TOKEN_FILE.read_text().strip()
        if t:
            return t
    except Exception:
        pass
    return TOKEN


PATH_MAP = {
    "/sdcard/": str(Path.home() / ".local/share/waydroid/data/media/0/"),
    "/storage/emulated/0/": str(Path.home() / ".local/share/waydroid/data/media/0/"),
}


COMMANDS = {
    "snes":       ["flatpak", "run", "org.libretro.RetroArch",
                   "-L", "snes9x", "{rom}"],
    "megadrive":  ["flatpak", "run", "org.libretro.RetroArch",
                   "-L", "genesis_plus_gx", "{rom}"],
    "gba":        ["flatpak", "run", "org.libretro.RetroArch",
                   "-L", "mgba", "{rom}"],
    "ps1":        ["flatpak", "run", "org.duckstation.DuckStation", "{rom}"],
    "psp":        ["flatpak", "run", "org.ppsspp.PPSSPP", "{rom}"],
    "gamecube":   ["flatpak", "run", "org.DolphinEmu.dolphin-emu",
                   "-b", "-e", "{rom}"],
    "ps2": ["/home/deck/Applications/pcsx2-stable",
        "-batch", "-fullscreen", "--", "{rom}"],
}
COMMANDS["psx"] = COMMANDS["ps1"]
COMMANDS["gc"] = COMMANDS["gamecube"]


_EMU_JSON = Path.home() / "Documents/iisu-bridge/emulators.json"


def effective_commands() -> dict:
    cmds = dict(COMMANDS)
    try:
        if _EMU_JSON.is_file():
            for _sys, _cmd in json.loads(_EMU_JSON.read_text()).items():
                if isinstance(_cmd, list) and _cmd:
                    cmds[_sys] = _cmd
    except Exception as e:
        print(f"[config] could not read {_EMU_JSON}: {e}", flush=True)
    return cmds


CORE_TO_SYSTEM = {
    "snes9x": "snes",
    "genesis_plus_gx": "megadrive",
    "mgba": "gba",
}


MANAGE_IISU = True
IISU_PACKAGE = "com.iisulauncher"
IISU_LAUNCH_COMPONENT = "com.iisulauncher/.launcher.StartupSafeModeActivity"


def _waydroid_shell(*args: str):
    cmd = ["sudo", "-n", "waydroid", "shell", "--"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            print(f"[iisu] {' '.join(args)} failed rc={r.returncode}: "
                  f"{(r.stderr or r.stdout).strip()}", flush=True)
    except Exception as e:
        print(f"[iisu] {' '.join(args)} error: {e} "
              "(is the sudoers rule for waydroid in place?)", flush=True)


MEDIA_PARENTS = [
    str(Path.home() / ".local/share/waydroid/data"),
    str(Path.home() / ".local/share/waydroid/data/media"),
    str(Path.home() / ".local/share/waydroid/data/media/0"),
]


def ensure_traversal_perms():
    print("[perms] re-opening traversal perms on media parents", flush=True)
    for d in MEDIA_PARENTS:
        try:
            r = subprocess.run(["sudo", "-n", "/usr/bin/chmod", "o+x", d],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                print(f"[perms] ok      {d}", flush=True)
            else:
                print(f"[perms] FAILED rc={r.returncode} {d}: "
                      f"{(r.stderr or r.stdout).strip()} "
                      "(sudoers rule mismatch? paths must match EXACTLY)",
                      flush=True)
        except Exception as e:
            print(f"[perms] chmod {d} failed: {e}", flush=True)


def stop_iisu():
    print("[iisu] stopping frontend", flush=True)
    _waydroid_shell("am", "force-stop", IISU_PACKAGE)


def start_iisu():
    print("[iisu] relaunching frontend", flush=True)
    _waydroid_shell("am", "start", "-n", IISU_LAUNCH_COMPONENT)


_current = {"proc": None, "lock": threading.Lock()}


def translate_path(android_path: str) -> str | None:
    for prefix, host_prefix in PATH_MAP.items():
        if android_path.startswith(prefix):
            return host_prefix.rstrip("/") + "/" + android_path[len(prefix):]
    return None


def resolve_core_path(core: str) -> str:
    base = Path(core).name
    for suf in ("_libretro_android.so", "_libretro.so", ".so"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    if base.endswith("_libretro"):
        base = base[: -len("_libretro")]
    for cand in (
        Path.home() / f".var/app/org.libretro.RetroArch/config/retroarch/cores/{base}_libretro.so",
        Path.home() / f".config/retroarch/cores/{base}_libretro.so",
    ):
        if cand.is_file():
            return str(cand)
    return f"{base}_libretro"


def unwrap_android_path(p: str) -> str:
    for m in ("/storage/emulated/0/", "/sdcard/"):
        i = p.rfind(m)
        if i > 0:
            return p[i:]
    return p


def redirect_ps3(rom_host: str) -> str:
    try:
        p = Path(rom_host)
        if p.is_file() and rom_host.endswith(".ps3"):
            cand = Path(rom_host + ".dir")
            if cand.is_dir():
                p = cand
                rom_host = str(cand)
        if p.is_dir():
            eb = p / "PS3_GAME" / "USRDIR" / "EBOOT.BIN"
            if eb.is_file():
                return str(eb)
    except PermissionError:
        pass
    return rom_host


def resolve_system(payload: dict) -> str | None:
    if "system" in payload:
        return payload["system"]
    core = payload.get("core", "")

    base = Path(core).name.replace("_libretro_android.so", "") \
                         .replace("_libretro.so", "")
    if not base:
        return None


    return CORE_TO_SYSTEM.get(base, "retroarch")


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in ("/launch", "/status"):
            return self._reply(404, {"error": "unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self._reply(400, {"error": "bad json"})

        if payload.get("token") != get_token():
            return self._reply(403, {"error": "bad token"})


        if self.path == "/status":
            with _current["lock"]:
                running = (_current["proc"] is not None
                           and _current["proc"].poll() is None)
            return self._reply(200, {"running": running})

        print(f"[req] /launch system={payload.get('system')!r} "
              f"core={payload.get('core')!r} rom={payload.get('rom')!r}",
              flush=True)
        cmds = effective_commands()
        system = resolve_system(payload)
        if system not in cmds:
            return self._reply(400, {"error": f"unknown system: {system!r}",
                                     "known": sorted(cmds)})

        template = cmds[system]
        uses_raw = any("{raw}" in p for p in template)
        uses_core = any("{core}" in p for p in template)

        rom_android = (payload.get("rom") or "").strip()
        if uses_raw:


            rom_host = rom_android.strip()
            if not rom_host:
                return self._reply(400, {"error": "empty rom value"})
        else:
            _unwrapped = unwrap_android_path(rom_android)
            if _unwrapped != rom_android:
                print(f"[unwrap] {rom_android!r} -> {_unwrapped!r}", flush=True)
                rom_android = _unwrapped
            rom_host = translate_path(rom_android)

            def rom_ok() -> bool:
                try:
                    if rom_host is None:
                        return False
                    p = Path(rom_host)

                    return p.is_file() or p.is_dir()
                except PermissionError:
                    return False

            if not rom_ok():

                ensure_traversal_perms()
                if not rom_ok():
                    print(f"[reject] rom not found: android={rom_android!r} "
                          f"-> host={rom_host!r} "
                          f"exists={rom_host is not None and Path(rom_host).exists()}",
                          flush=True)
                    return self._reply(400, {"error": "rom not found",
                                             "android_path": rom_android,
                                             "host_path": rom_host})

            _pre = rom_host
            rom_host = redirect_ps3(rom_host)
            if rom_host != _pre:
                print(f"[ps3] redirected {_pre!r} -> {rom_host!r}", flush=True)

        core_host = ""
        if uses_core:
            core_val = payload.get("core", "")
            if not core_val:
                return self._reply(400, {"error": "this system needs a 'core' "
                                                  "(sent by the RetroArch stub)"})
            core_host = resolve_core_path(core_val)

        cmd = [part.replace("{rom}", rom_host)
                   .replace("{raw}", rom_host)
                   .replace("{core}", core_host)
               for part in template]

        with _current["lock"]:
            if _current["proc"] and _current["proc"].poll() is None:
                return self._reply(409, {"error": "emulator already running"})
            print(f"[launch] {shlex.join(cmd)}", flush=True)
            try:
                _current["proc"] = subprocess.Popen(cmd)
            except FileNotFoundError:
                print(f"[reject] emulator executable not found: {cmd[0]!r}",
                      flush=True)
                return self._reply(500, {"error": "emulator executable not "
                                                  "found", "exe": cmd[0]})
            except Exception as e:
                print(f"[reject] failed to start emulator: {e}", flush=True)
                return self._reply(500, {"error": f"failed to start: {e}"})
            threading.Thread(target=self._wait_and_report,
                             args=(_current["proc"],), daemon=True).start()
            if MANAGE_IISU:
                threading.Timer(2.0, stop_iisu).start()

        return self._reply(200, {"status": "launched", "system": system,
                                 "rom": rom_host})

    def _wait_and_report(self, proc: subprocess.Popen):
        rc = proc.wait()
        print(f"[exit] emulator exited with code {rc}", flush=True)
        if MANAGE_IISU:
            start_iisu()

    def log_message(self, fmt, *args):
        pass


def main():
    if TOKEN == "CHANGE_ME":
        print("WARNING: set a real TOKEN before regular use.", flush=True)
    ensure_traversal_perms()


    import time
    server = None
    announced = False
    while server is None:
        try:
            server = ThreadingHTTPServer((BIND_ADDR, BIND_PORT), Handler)
        except OSError:
            if not announced:
                print(f"[wait] {BIND_ADDR} not available yet "
                      "(Waydroid container not up?) — retrying every 5s",
                      flush=True)
                announced = True
            time.sleep(5)
    print(f"iiSU bridge daemon listening on {BIND_ADDR}:{BIND_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

