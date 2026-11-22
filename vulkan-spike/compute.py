"""S2 of the Vulkan spike: compile double.comp with the SDK's glslc into a header, build
compute.cpp against the SDK's loader and run it with the drivers and layers of each system.

usage: compute.py <linux|mac|windows> <out dir>   (reads <out dir>/sdk.json from sdk.py)
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import time

platform, out = sys.argv[1], os.path.abspath(sys.argv[2])
here = os.path.dirname(os.path.abspath(__file__))
build = os.path.join(out, "build")
os.makedirs(build, exist_ok=True)
sdk = json.load(open(os.path.join(out, "sdk.json")))
report_lines = []


def report(*parts):
    line = " ".join(str(p) for p in parts)
    print(line, flush=True)
    report_lines.append(line)


def run(name, args, env_add=None, env=None, timeout=300):
    """Runs a command with extra environment, logs to out/s2-<name>.txt and the report."""
    environment = dict(env or os.environ)
    environment.update(env_add or {})
    start = time.monotonic()
    try:
        done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment, timeout=timeout)
        code = done.returncode
        stdout, stderr = done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        code, stdout, stderr = "timeout", "", ""
    except OSError as e:
        code, stdout, stderr = "oserror", "", str(e)
    seconds = time.monotonic() - start
    if isinstance(code, int) and code < 0 and platform == "windows":
        code = f"{code} (0x{code & 0xFFFFFFFF:08X})"
    elif isinstance(code, int) and code > 255 and platform == "windows":
        code = f"{code} (0x{code:08X})"
    text = (f"$ {' '.join(args)}\nenv: {env_add or {}}\nexit: {code}\nseconds: {seconds:.1f}\n"
            f"--- stdout\n{stdout}\n--- stderr\n{stderr}")
    with open(os.path.join(out, f"s2-{name}.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    report(f"=== {name}: exit {code}, {seconds:.1f} s, env {env_add or {}}")
    for label, stream in (("stdout", stdout), ("stderr", stderr)):
        lines = stream.strip().splitlines()
        if lines:
            shown = lines if len(lines) <= 40 else lines[:20] + [f"... {len(lines) - 40} lines ..."] + lines[-20:]
            report(f"  [{label}]\n    " + "\n    ".join(shown))
    return code, stdout, stderr


def msvc_environment():
    vswhere = os.path.join(os.environ["ProgramFiles(x86)"], "Microsoft Visual Studio", "Installer", "vswhere.exe")
    path = subprocess.run([vswhere, "-latest", "-property", "installationPath"], stdout=subprocess.PIPE,
                          check=True).stdout.decode().strip()
    vcvars = os.path.join(path, "VC", "Auxiliary", "Build", "vcvars64.bat")
    dump = subprocess.run(f'cmd /c ""{vcvars}" > nul && set"', stdout=subprocess.PIPE, shell=True,
                          check=True).stdout.decode("utf-8", "replace")
    environment = {}
    for line in dump.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            environment[key] = value
    report("msvc:", path)
    return environment


def msvc_tool(environment, name):
    # CreateProcess searches the PATH of this process, not the one handed to the child
    path = next(v for k, v in environment.items() if k.upper() == "PATH")
    return shutil.which(name, path=path)


def main():
    exe = ".exe" if platform == "windows" else ""
    glslc = os.path.join(sdk["bin"], "glslc" + exe)
    run("glslc-version", [glslc, "--version"])
    header = os.path.join(build, "double.spv.h")
    run("glslc", [glslc, "-mfmt=c", os.path.join(here, "double.comp"), "-o", header])
    if os.path.exists(header):
        with open(header) as f:
            report("double.spv.h starts with:", f.read(120).replace("\n", " "))

    source = os.path.join(here, "compute.cpp")
    program = os.path.join(build, "compute" + exe)
    msvc = None
    if platform == "windows":
        msvc = msvc_environment()
        run("compile", [msvc_tool(msvc, "cl"), "/nologo", "/EHsc", "/std:c++17", "/W3", "/I", build, "/I", sdk["include"], source,
                        f"/Fo{build}\\", f"/Fe{program}", "/link", os.path.join(sdk["lib"], "vulkan-1.lib")],
            env=msvc)
        run("dependents", [msvc_tool(msvc, "dumpbin"), "/nologo", "/dependents", program], env=msvc)
    else:
        compiler = "g++" if platform == "linux" else "clang++"
        run("compile", [compiler, "-std=c++17", "-O1", "-Wall", "-I", build, "-I", sdk["include"], source,
                        "-L", sdk["lib"], "-lvulkan", f"-Wl,-rpath,{sdk['lib']}", "-o", program])
        run("dependents", ["ldd", program] if platform == "linux" else ["otool", "-L", "-l", program])
    if not os.path.exists(program):
        report("no program, stopping")
        return

    layers = {"VK_ADD_LAYER_PATH": sdk["explicit_layer_d"] or "", "VK_INSTANCE_LAYERS": "VK_LAYER_KHRONOS_validation"}
    debug = {"VK_LOADER_DEBUG": "error,warn"}

    if platform == "linux":
        report("icd.d before mesa:", glob.glob("/usr/share/vulkan/icd.d/*") + glob.glob("/etc/vulkan/icd.d/*"))
        run("no-driver", [program])
        run("no-driver-loader-debug", [program], debug)
        run("no-driver-layers", [program, "--misuse"], layers)
        start = time.monotonic()
        subprocess.run("sudo apt-get update -q && sudo apt-get install -q -y mesa-vulkan-drivers", shell=True,
                       check=True, stdout=subprocess.DEVNULL)
        report(f"apt-get install mesa-vulkan-drivers: {time.monotonic() - start:.1f} s")
        report("icd.d after mesa:", glob.glob("/usr/share/vulkan/icd.d/*"))
        lavapipe = {"VK_DRIVER_FILES": next(iter(glob.glob("/usr/share/vulkan/icd.d/lvp_icd*.json")), "")}
        run("all-drivers", [program])
        run("lavapipe", [program], lavapipe)
        run("lavapipe-layers-misuse", [program, "--misuse"], {**lavapipe, **layers})
        run("lavapipe-layers-clean", [program], {**lavapipe, **layers})
        run("vulkaninfo", [os.path.join(sdk["bin"], "vulkaninfo"), "--summary"], {**lavapipe, "LD_LIBRARY_PATH": sdk["lib"]})
    elif platform == "mac":
        run("no-driver", [program])
        run("no-driver-loader-debug", [program], debug)
        moltenvk = {"VK_DRIVER_FILES": sdk["moltenvk_icd"] or ""}
        kosmickrisp = {"VK_DRIVER_FILES": sdk["kosmickrisp_icd"] or ""}
        run("moltenvk", [program], moltenvk)
        code, _, _ = run("kosmickrisp", [program], kosmickrisp)
        if code != 0:
            run("kosmickrisp-loader-debug", [program], {**kosmickrisp, **debug})
        run("both-drivers", [program],
            {"VK_DRIVER_FILES": os.pathsep.join(p for p in (sdk["moltenvk_icd"], sdk["kosmickrisp_icd"]) if p)})
        run("moltenvk-layers-misuse", [program, "--misuse"], {**moltenvk, **layers})
        run("moltenvk-layers-clean", [program], {**moltenvk, **layers})
        vulkaninfo = os.path.join(sdk["bin"], "vulkaninfo")
        run("vulkaninfo-moltenvk", [vulkaninfo, "--summary"], moltenvk)
        run("vulkaninfo-kosmickrisp", [vulkaninfo, "--summary"], kosmickrisp)
        run("sw_vers", ["sw_vers"])
        run("system_profiler", ["system_profiler", "SPDisplaysDataType"])
    else:
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        report("System32 vulkan-1.dll:", os.path.exists(os.path.join(system32, "vulkan-1.dll")),
               "vulkaninfo.exe:", os.path.exists(os.path.join(system32, "vulkaninfo.exe")))
        report("vulkan-1.dll in the SDK:", glob.glob(os.path.join(sdk["root"], "**", "vulkan-1.dll"), recursive=True))
        run("system-loader", [program])
        run("system-loader-debug", [program], debug)
        sdk_path = {"PATH": sdk["bin"] + os.pathsep + os.environ["PATH"]}
        run("sdk-bin-in-path", [program], sdk_path)
        run("sdk-bin-in-path-debug", [program], {**sdk_path, **debug})
        run("layers-misuse", [program, "--misuse"], {**sdk_path, **layers})
        # the loader of the SDK next to the program: what build-script would do with a dll of a port
        dlls = glob.glob(os.path.join(sdk["bin"], "vulkan-1.dll"))
        if dlls:
            shutil.copy(dlls[0], build)
            run("dll-next-to-program-debug", [program], debug)
        run("vulkaninfo", [os.path.join(sdk["bin"], "vulkaninfo" + exe), "--summary"], sdk_path)

    with open(os.path.join(out, "s2-report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))


main()
