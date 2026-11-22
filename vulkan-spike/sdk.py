"""S1 of the Vulkan spike: download the LunarG SDK pinned by version and SHA-256, install it
silently into a directory of our own, and record size, time, layout, licenses and whatever the
installer writes outside that directory.

usage: sdk.py <linux|mac|windows> <work dir> <out dir>
"""

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

VERSION = os.environ.get("SDK_VERSION", "1.4.363.1")
FILES = {"linux": "vulkan_sdk.tar.xz", "mac": "vulkan_sdk.zip", "windows": "vulkan_sdk.exe"}

platform, work, out = sys.argv[1], os.path.abspath(sys.argv[2]), os.path.abspath(sys.argv[3])
os.makedirs(work, exist_ok=True)
os.makedirs(out, exist_ok=True)
report_lines = []


def report(*parts):
    line = " ".join(str(p) for p in parts)
    print(line, flush=True)
    report_lines.append(line)


def save(name, text):
    with open(os.path.join(out, name), "w", encoding="utf-8") as f:
        f.write(text)


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "vulkan-spike"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def run(args, log, timeout=1800, **kwargs):
    """Runs a command, writes its output to out/<log>, returns (code, seconds, output)."""
    start = time.monotonic()
    try:
        done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, **kwargs)
        code, output = done.returncode, done.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, output = "timeout", (e.stdout or b"").decode("utf-8", "replace")
    except OSError as e:
        code, output = "oserror", str(e)
    seconds = time.monotonic() - start
    save(log, f"$ {args}\nexit: {code}\nseconds: {seconds:.1f}\n\n{output}")
    return code, seconds, output


def tree_size(root):
    total, count = 0, 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                if not os.path.islink(path):
                    total += os.path.getsize(path)
                    count += 1
            except OSError:
                pass
    return total, count


def mb(n):
    return f"{n / 1e6:.1f} MB"


# --- outside writes -------------------------------------------------------------------------

def windows_registry():
    keys = [
        r"HKLM\SOFTWARE\Khronos",
        r"HKLM\SOFTWARE\WOW6432Node\Khronos",
        r"HKCU\SOFTWARE\Khronos",
        r"HKLM\SOFTWARE\LunarG",
        r"HKCU\SOFTWARE\LunarG",
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        r"HKCU\Environment",
    ]
    text = []
    for key in keys:
        done = subprocess.run(["reg", "query", key, "/s"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text.append(f"### {key}\n" + done.stdout.decode("utf-8", "replace"))
    return "\n".join(text).splitlines()


def newer_files(roots, since, skip):
    """Files and directories under roots changed after since, up to a depth per root."""
    found = []
    for root, depth in roots:
        if not os.path.isdir(root):
            continue
        base = root.rstrip("\\/").count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            if any(dirpath.startswith(s) for s in skip):
                dirnames[:] = []
                continue
            if dirpath.count(os.sep) - base >= depth:
                dirnames[:] = []
            for name in filenames + dirnames:
                path = os.path.join(dirpath, name)
                try:
                    if os.lstat(path).st_mtime > since:
                        found.append(path)
                except OSError:
                    pass
    return found


def outside_roots():
    home = os.path.expanduser("~")
    if platform == "mac":
        return [("/usr/local", 6), ("/Library", 3), ("/etc", 3), ("/private/etc", 3),
                ("/Applications", 2), ("/opt", 2), (home, 4)]
    if platform == "windows":
        env = os.environ
        return [(env.get("ProgramData", r"C:\ProgramData"), 4),
                (env.get("APPDATA", ""), 4),
                (env.get("LOCALAPPDATA", ""), 3),
                (os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32"), 1),
                (os.path.join(env.get("SystemRoot", r"C:\Windows"), "SysWOW64"), 1),
                (env.get("ProgramFiles", r"C:\Program Files"), 1),
                (env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), 1),
                (os.path.join(home, "Desktop"), 2)]
    return []


def outside_skip():
    skip = [work, out, os.path.abspath(".")]
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        skip.append(runner_temp)
    if platform == "windows":
        skip.append(os.path.join(os.environ.get("LOCALAPPDATA", "?"), "Temp"))
    return skip


# --- the installers -------------------------------------------------------------------------

def install(archive, root, label, extra=(), as_basic_user=False):
    """Installs into root, returns seconds or None; logs in out/install-<label>.txt."""
    if platform == "linux":
        os.makedirs(root, exist_ok=True)
        code, seconds, _ = run(["tar", "-xJf", archive, "-C", root], f"install-{label}.txt")
        return seconds if code == 0 else None

    if platform == "mac":
        unpacked = os.path.join(work, "unpacked")
        if not os.path.isdir(unpacked):
            code, seconds, _ = run(["ditto", "-x", "-k", archive, unpacked], "unzip.txt")
            report(f"unzip: exit {code}, {seconds:.1f} s")
            report("zip contents:", os.listdir(unpacked))
        apps = sorted(n for n in os.listdir(unpacked) if n.endswith(".app"))
        app = os.path.join(unpacked, apps[0])
        executables = os.listdir(os.path.join(app, "Contents", "MacOS"))
        report("executables in", apps[0], executables)
        program = os.path.join(app, "Contents", "MacOS", executables[0])
        if not os.path.exists(os.path.join(out, "installer-help.txt")):
            code, seconds, output = run([program, "--help"], "installer-help.txt", timeout=60)
            report(f"installer --help: exit {code}, {len(output)} bytes of output")
    else:
        program = archive

    args = [program, "--root", root, "--accept-licenses", "--default-answer", "--confirm-command",
            "install", *extra]
    if as_basic_user:
        # runas with the basic-user trust level drops the admin rights of the runner's token.
        # It starts the command asynchronously, so a script writes a marker when it is done.
        script = os.path.join(work, f"install-{label}.cmd")
        log = os.path.join(out, f"install-{label}.txt")
        marker = os.path.join(work, f"install-{label}.done")
        quoted = " ".join(f'"{a}"' for a in args)
        with open(script, "w") as f:
            f.write(f"@echo off\r\n{quoted} > \"{log}\" 2>&1\r\necho %ERRORLEVEL% > \"{marker}\"\r\n")
        start = time.monotonic()
        done = subprocess.run(["runas", "/trustlevel:0x20000", script], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=60)
        report(f"runas: exit {done.returncode}: {done.stdout.decode('utf-8', 'replace').strip()}")
        while time.monotonic() - start < 600 and not os.path.exists(marker):
            time.sleep(5)
        seconds = time.monotonic() - start
        if not os.path.exists(marker):
            report(f"install {label}: no marker after {seconds:.0f} s")
            return None
        code = open(marker).read().strip()
        report(f"install {label}: exit {code}, {seconds:.1f} s")
        return seconds if code == "0" else None

    code, seconds, output = run(args, f"install-{label}.txt", timeout=1800)
    report(f"install {label}: exit {code}, {seconds:.1f} s, args {args[1:]}")
    tail = "\n".join(output.splitlines()[-15:])
    report("  last lines:\n    " + tail.replace("\n", "\n    "))
    return seconds if code == 0 else None


def requested_execution_level(exe):
    data = open(exe, "rb").read()
    match = re.search(rb'requestedExecutionLevel[^>]*level="([^"]+)"', data)
    return match.group(1).decode() if match else "no manifest level found"


# --- layout ---------------------------------------------------------------------------------

PATTERNS = ["glslc", "glslc.exe", "slangc", "slangc.exe", "vulkaninfo", "vulkaninfo.exe", "vulkaninfoSDK.exe",
            "libvulkan.so*", "libvulkan*.dylib", "vulkan-1.dll", "vulkan-1.lib", "*VkLayer_khronos_validation*",
            "*MoltenVK*", "*kosmickrisp*", "vkconfig*", "setup-env.sh", "vulkan.framework"]


def layout(root):
    hits, layer_dirs, licenses = [], [], []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for name in filenames + dirnames:
            if any(fnmatch.fnmatch(name, p) for p in PATTERNS):
                path = os.path.join(dirpath, name)
                size = os.path.getsize(path) if os.path.isfile(path) and not os.path.islink(path) else 0
                link = f" -> {os.readlink(path)}" if os.path.islink(path) else ""
                hits.append(f"{os.path.join(rel, name)}  {size}{link}")
            if re.search(r"licen[cs]e|copying|eula", name, re.I) and rel.count(os.sep) < 3:
                licenses.append(os.path.join(rel, name))
        if os.path.basename(dirpath) in ("explicit_layer.d", "implicit_layer.d", "icd.d"):
            layer_dirs.append(rel)
    return hits, layer_dirs, licenses


def tree(root, depth=3):
    lines = []
    base = root.rstrip("\\/").count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        level = dirpath.count(os.sep) - base
        if level >= depth:
            dirnames[:] = []
            continue
        dirnames.sort()
        size, count = tree_size(dirpath)
        lines.append(f"{'  ' * level}{os.path.basename(dirpath)}/  {mb(size)}, {count} files")
    return "\n".join(lines)


def find_sdk_dir(root):
    """The directory with bin/ and lib/ (VULKAN_SDK in LunarG's terms)."""
    for dirpath, dirnames, filenames in os.walk(root):
        names = {n.lower() for n in filenames}
        if "glslc" in names or "glslc.exe" in names:
            return os.path.dirname(dirpath)
    return None


def first(root, *names):
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            if name in names:
                return os.path.join(dirpath, name)
    return None


def main():
    report(f"platform {platform}, SDK {VERSION}, python {sys.version.split()[0]}")
    latest = json.loads(fetch("https://vulkan.lunarg.com/sdk/latest.json"))
    report("latest.json:", json.dumps(latest))
    sha_json = json.loads(fetch(f"https://sdk.lunarg.com/sdk/sha/{VERSION}/{platform}/{FILES[platform]}.json"))
    report("sha json:", json.dumps(sha_json))

    downloads = os.path.join(work, "downloads")
    os.makedirs(downloads, exist_ok=True)
    archive = os.path.join(downloads, sha_json["file"])
    url = f"https://sdk.lunarg.com/sdk/download/{VERSION}/{platform}/{sha_json['file']}"
    start = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "vulkan-spike"})
    with urllib.request.urlopen(request, timeout=600) as response, open(archive, "wb") as f:
        report("download url after redirects:", response.geturl())
        shutil.copyfileobj(response, f, 1 << 20)
    download_seconds = time.monotonic() - start
    digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    report(f"download: {mb(os.path.getsize(archive))} in {download_seconds:.1f} s")
    report(f"sha256 {digest} {'matches' if digest == sha_json['sha'] else 'DOES NOT MATCH ' + sha_json['sha']}")
    if digest != sha_json["sha"]:
        sys.exit("sha256 mismatch")

    if platform == "windows":
        report("requestedExecutionLevel of the installer:", requested_execution_level(archive))
        code, seconds, output = run([archive, "--help"], "installer-help.txt", timeout=60)
        report(f"installer --help: exit {code}, {len(output)} bytes of output")
    if platform == "windows":
        done = subprocess.run(["net", "session"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        report("admin token (net session):", "yes" if done.returncode == 0 else "no")
    if platform == "mac":
        report("user:", os.environ.get("USER"), "uid", os.getuid())

    # the install build-script would do: copy only, no admin, its own root
    root = os.path.join(work, "sdk", VERSION)
    registry_before = windows_registry() if platform == "windows" else []
    since = time.time() - 1
    seconds = install(archive, root, "copy-only", extra=() if platform == "linux" else ("copy_only=1",))
    if seconds is None:
        report("copy-only install failed")
    time.sleep(1)
    outside = newer_files(outside_roots(), since, outside_skip())
    save("outside-copy-only.txt", "\n".join(outside))
    report(f"changed outside the root during the copy-only install: {len(outside)} paths (outside-copy-only.txt)")
    for path in outside[:40]:
        report("  ", path)
    if platform == "windows":
        registry_after = windows_registry()
        added = [l for l in registry_after if l not in registry_before]
        removed = [l for l in registry_before if l not in registry_after]
        save("registry-copy-only.txt", "added:\n" + "\n".join(added) + "\n\nremoved:\n" + "\n".join(removed))
        report(f"registry during the copy-only install: {len(added)} lines added, {len(removed)} removed")
        for line in added[:40]:
            report("  +", line)

    size, count = tree_size(root)
    archive_size = os.path.getsize(archive)
    report(f"installed: {mb(size)} in {count} files, archive {mb(archive_size)}, install {seconds} s")
    save("tree.txt", tree(root, 4))
    hits, layer_dirs, licenses = layout(root)
    save("layout.txt", "\n".join(hits))
    report("layout (relative to the root):")
    for hit in hits:
        report("  ", hit)
    report("layer and icd directories:", layer_dirs)
    for rel in layer_dirs:
        directory = os.path.join(root, rel)
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            report(f"--- {os.path.join(rel, name)}")
            if name.endswith(".json") and os.path.getsize(path) < 4000:
                report(open(path, encoding="utf-8", errors="replace").read())
            elif name.endswith(".json"):
                data = json.load(open(path, encoding="utf-8"))
                layer = data.get("layer") or data.get("ICD") or {}
                report("  library_path:", layer.get("library_path"), "api_version:", layer.get("api_version"))
    report("license files:", licenses)
    urls = set()
    for rel in licenses:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            text = open(path, encoding="utf-8", errors="replace").read()
            urls.update(re.findall(r"https?://[^\s\"'<>)]+", text))
            report(f"--- {rel}: {len(text)} chars, first lines:")
            report("    " + "\n    ".join(text.strip().splitlines()[:8]))
    report("urls in license files:", sorted(urls)[:40])

    sdk = find_sdk_dir(root)
    info = {
        "root": root,
        "vulkan_sdk": sdk,
        "bin": os.path.join(sdk, "Bin" if platform == "windows" else "bin") if sdk else None,
        "lib": os.path.join(sdk, "Lib" if platform == "windows" else "lib") if sdk else None,
        "include": os.path.join(sdk, "Include" if platform == "windows" else "include") if sdk else None,
        "explicit_layer_d": next((os.path.join(root, d) for d in layer_dirs if d.endswith("explicit_layer.d")
                                  and "iOS" not in d), None),
        "moltenvk_icd": first(os.path.join(root, "macOS"), "MoltenVK_icd.json") if platform == "mac" else None,
        "kosmickrisp_icd": first(os.path.join(root, "macOS"), "libkosmickrisp_icd.json") if platform == "mac" else None,
        "install_seconds": seconds,
        "download_seconds": download_seconds,
        "archive_bytes": archive_size,
        "installed_bytes": size,
        "installed_files": count,
    }
    if platform == "windows":
        # where the validation layer's json lies on windows (Bin, next to the dll)
        layer_json = first(root, "VkLayer_khronos_validation.json")
        info["explicit_layer_d"] = info["explicit_layer_d"] or (os.path.dirname(layer_json) if layer_json else None)
    report("sdk.json:", json.dumps(info, indent=2))
    save("sdk.json", json.dumps(info, indent=2))

    # windows only: what the default install writes outside the root, and whether it runs without admin
    if platform == "windows":
        registry_before = windows_registry()
        since = time.time() - 1
        default_root = os.path.join(work, "sdk-default", VERSION)
        install(archive, default_root, "default")
        time.sleep(1)
        outside = newer_files(outside_roots(), since, outside_skip())
        save("outside-default.txt", "\n".join(outside))
        report(f"changed outside the root during the default install: {len(outside)} paths (outside-default.txt)")
        for path in outside[:40]:
            report("  ", path)
        registry_after = windows_registry()
        added = [l for l in registry_after if l not in registry_before]
        save("registry-default.txt", "added:\n" + "\n".join(added))
        report(f"registry during the default install: {len(added)} lines added")
        for line in added[:60]:
            report("  +", line)
        basic_root = os.path.join(work, "sdk-basic-user", VERSION)
        install(archive, basic_root, "basic-user", extra=("copy_only=1",), as_basic_user=True)
        if os.path.isdir(basic_root):
            size, count = tree_size(basic_root)
            report(f"basic-user install root: {mb(size)} in {count} files")
        else:
            report("basic-user install root does not exist")

    save("s1-report.txt", "\n".join(report_lines))


main()
