#!/usr/bin/env python3
# Runs the regression scenarios against a build-script binary. A scenario is a directory with a
# scenario.toml: the repository and commit of its sources, if it has any, and the commands to run.
# The files in its project/ go on top of the sources, or are the project.
#
#   python3 run.py --build ../build/target/release/build-script            every scenario of this system
#   python3 run.py --build ... --kind c-cpp jvm                             the C and C++ and the JVM ones
#   python3 run.py --build ... cJSON new-kotlin                             these
#   python3 run.py --build ... --slow                                       with those that take hours
#   python3 run.py --build ... --device emulator-5580                       with the steps that start apps on it
#   python3 run.py --build ... --device emulator-5580 --device-only         only the scenarios with such steps
#
# BUILD_SCRIPT_HOME is .home/ unless it is set. Logs go to .logs/, the projects are built in .work/.
import argparse
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios"

SYSTEM = {"darwin": "macos", "linux": "linux", "win32": "windows"}[sys.platform]

# a JVM program that ends with these did not link, the names alone may be in its output
LINKAGE_ERRORS = re.compile(
    r"Exception in thread \"|java\.lang\.(NoSuchMethodError|NoClassDefFoundError|ClassNotFoundException|LinkageError|"
    r"UnsatisfiedLinkError|ExceptionInInitializerError|AbstractMethodError|IncompatibleClassChangeError)"
)

# a build that is up to date compiles and links nothing
WORK_DONE = re.compile(r"Compiling|Linking|Done:")

IN_PIPELINE = os.environ.get("GITHUB_ACTIONS") == "true"


class Scenario:
    def __init__(self, directory):
        self.directory = directory
        self.kind = directory.parent.name
        self.name = directory.name
        self.config = tomllib.loads((directory / "scenario.toml").read_text())
        self.about = (directory / "scenario.toml").read_text().splitlines()[0].lstrip("# ")

    def runs_here(self, slow):
        platforms = self.config.get("platforms", ["macos", "linux", "windows"])
        return SYSTEM in platforms and (slow or not self.config.get("slow", False))

    def starts_apps(self):
        return any(isinstance(entry, dict) and "started" in entry for entry in self.config["steps"])


def remove_tree(directory):
    """Like shutil.rmtree, also the read-only files git writes on Windows"""
    def writable(function, path, _):
        os.chmod(path, stat.S_IWRITE)
        function(path)

    if directory.exists():
        shutil.rmtree(directory, onexc=writable)


def sources(scenario):
    """A checkout of the commit, fetched once into .sources/"""
    url, commit = scenario.config["git"], scenario.config["commit"]
    checkout = ROOT / ".sources" / f"{scenario.name}-{commit[:12]}"

    if not checkout.is_dir():
        partial = checkout.with_name(checkout.name + ".partial")
        remove_tree(partial)
        partial.mkdir(parents=True)
        for command in [["init", "--quiet"], ["fetch", "--quiet", "--depth", "1", url, commit], ["checkout", "--quiet", "FETCH_HEAD"]]:
            subprocess.run(["git", "-C", str(partial), *command], check=True)
        remove_tree(partial / ".git")
        partial.rename(checkout)

    return checkout


def prepare(scenario):
    work = ROOT / ".work" / scenario.kind / scenario.name
    remove_tree(work)

    if "git" in scenario.config:
        shutil.copytree(sources(scenario), work)
    else:
        work.mkdir(parents=True)

    project = scenario.directory / "project"
    if project.is_dir():
        shutil.copytree(project, work, dirs_exist_ok=True)

    return work


def step_of(entry):
    """A step as written, "build again" checks that nothing is built again"""
    if isinstance(entry, str):
        entry = {"command": entry}

    words = shlex.split(entry["command"])
    again = words[:2] == ["build", "again"]
    arguments = ["build", *words[2:]] if again else words

    return {
        "label": entry["command"],
        "arguments": arguments,
        "again": again,
        "fails": entry.get("fails", False),
        "output": entry.get("output"),
        # lines with it are no linkage errors, like a warning of the project itself
        "harmless": entry.get("harmless"),
        # files below the project this step has to leave behind
        "files": entry.get("files", []),
        # a keystore this step and those after it sign with
        "release_key": entry.get("release_key"),
        # a file below the project this step changes first, the step has to build again
        "changed": entry.get("changed"),
        # the application id of an app this step starts on the device, without --device it is left out
        "started": entry.get("started"),
        "platforms": entry.get("platforms", ["macos", "linux", "windows"]),
        # programs that wait for input or serve forever have no run step
        "timeout": 300 if arguments[0] == "run" else 4 * 3600,
    }


def problem_of(step, code, output, work):
    """What is wrong with a step, None when it went as expected"""
    if code is None:
        return f"timed out after {step['timeout']}s"
    if step["fails"]:
        if code == 0:
            return "succeeded, but should fail"
    elif code != 0:
        return f"exit {code}"
    if step["output"] and step["output"] not in output:
        return f"no \"{step['output']}\" in the output"
    for file in step["files"]:
        if not (work / file).is_file():
            return f"no {file}"
    if step["changed"] and not WORK_DONE.search(output):
        return f"not built again after {step['changed']} changed"
    if step["again"] and ("Up to date" not in output or WORK_DONE.search(output)):
        return "not up to date"
    if step["arguments"][0] == "test" and not step["fails"] and "> Tests" not in output:
        return "no test summary"
    if step["arguments"][0] == "run":
        lines = [line for line in output.splitlines() if not (step["harmless"] and step["harmless"] in line)]
        if match := LINKAGE_ERRORS.search("\n".join(lines)):
            return match.group(0)
    return None


def create_release_key(keystore, environment):
    """A key only for this run, its password exists only in RELEASE_KEY_PASSWORD"""
    environment["RELEASE_KEY_PASSWORD"] = secrets.token_urlsafe(24)

    # from the JDK build-script installed in the steps before
    keytool = next(Path(environment["BUILD_SCRIPT_HOME"]).glob("jdks/*/**/bin/keytool*"))

    subprocess.run([keytool, "-genkeypair", "-keystore", keystore, "-alias", "release", "-keyalg", "RSA", "-keysize", "2048", "-validity", "2",
                    "-dname", "CN=regressions", "-storepass:env", "RELEASE_KEY_PASSWORD", "-keypass:env", "RELEASE_KEY_PASSWORD"],
                   env=environment, stdin=subprocess.DEVNULL, capture_output=True, check=True)


def adb_of(environment):
    """adb like build-script finds it: of ANDROID_HOME, ANDROID_SDK_ROOT or the SDK in its home, None before
    build-script installed it with the first app"""
    name = "adb.exe" if SYSTEM == "windows" else "adb"
    roots = [environment.get("ANDROID_HOME"), environment.get("ANDROID_SDK_ROOT"), Path(environment["BUILD_SCRIPT_HOME"]) / "android-sdk"]
    adbs = [Path(root) / "platform-tools" / name for root in roots if root]
    return next((adb for adb in adbs if adb.is_file()), None)


def adb(environment, *arguments):
    """What adb printed for the device of ANDROID_SERIAL"""
    return subprocess.run([adb_of(environment), "-s", environment["ANDROID_SERIAL"], *arguments], env=environment,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace").stdout


def remove_from_device(application_id, environment):
    """The app and the crashes of earlier runs off the device, so the step installs and starts it afresh"""
    if adb_of(environment) is None:
        return

    adb(environment, "uninstall", application_id)
    adb(environment, "logcat", "-b", "crash", "-c")


def problem_on_device(application_id, environment, log):
    """Why the app a step started does not run on the device, None when it runs. Its crash goes to the log."""
    # a crash in the first frames comes a moment after am start returned
    time.sleep(5)

    crashes = adb(environment, "logcat", "-b", "crash", "-d").splitlines()
    crashed = next((index for index, line in enumerate(crashes) if f"Process: {application_id}, PID" in line), None)

    if crashed is not None:
        with open(log, "a") as output_file:
            output_file.write("\n".join(crashes) + "\n")

        # its lines up to the next crash, the last cause names what is missing
        end = next((index for index in range(crashed + 1, len(crashes)) if "FATAL EXCEPTION" in crashes[index]), len(crashes))
        messages = [line.split(": ", 1)[-1] for line in crashes[crashed + 1:end]]
        cause = next((message for message in reversed(messages) if message.startswith("Caused by: ")), messages[0] if messages else "")

        # a class not found lists every dex file after "on path"
        return f"crashed: {cause.removeprefix('Caused by: ').split(' on path:')[0][:200]}"

    if not adb(environment, "shell", "pidof", application_id).strip():
        return "not running"

    return None


def run(scenario, build, logs, device):
    work = prepare(scenario)
    environment = dict(os.environ)
    extra = [path for path in scenario.config.get("path", []) if Path(path).is_dir()]
    environment["PATH"] = os.pathsep.join([*extra, environment["PATH"]])

    # build-script starts apps on it
    if device:
        environment["ANDROID_SERIAL"] = device

    failures = 0
    for index, entry in enumerate(scenario.config["steps"], 1):
        step = step_of(entry)
        if SYSTEM not in step["platforms"]:
            continue

        if step["started"] and not device:
            print(f"  skip  {step['label']} (no --device)")
            continue

        if step["changed"]:
            # one more line at the end changes the content, but not what it means
            with open(work / step["changed"], "a") as changed_file:
                changed_file.write("\n")

        if step["release_key"]:
            create_release_key(work / step["release_key"], environment)

        if step["started"]:
            remove_from_device(step["started"], environment)

        command = re.sub(r"[^\w.]+", "-", " ".join(step["arguments"][:2]))
        log = logs / f"{scenario.kind}-{scenario.name}-{index}-{command}.log"
        started = time.monotonic()

        with open(log, "w") as output_file:
            try:
                code = subprocess.run([build, *step["arguments"]], cwd=work, env=environment, stdin=subprocess.DEVNULL,
                                      stdout=output_file, stderr=subprocess.STDOUT, timeout=step["timeout"]).returncode
            except subprocess.TimeoutExpired:
                code = None

        output = log.read_text(errors="replace")
        problem = problem_of(step, code, output, work)
        if problem is None and step["started"]:
            problem = problem_on_device(step["started"], environment, log)

        seconds = round(time.monotonic() - started)
        last = next((line for line in reversed(output.splitlines()) if line.strip()), "")[:100]

        if problem is None:
            print(f"  ok    {step['label']} ({seconds}s) {last}")
            continue

        failures += 1
        print(f"  FAIL  {step['label']} ({seconds}s): {problem}, see {log.relative_to(ROOT)}")
        if IN_PIPELINE:
            print("::group::the end of the log")
            # with the crash of an app on the device
            print("\n".join(log.read_text(errors="replace").splitlines()[-80:]))
            print("::endgroup::")

        # what follows needs this step
        break

    return failures


def main():
    parser = argparse.ArgumentParser(description="Runs the regression scenarios against a build-script binary")
    parser.add_argument("names", nargs="*", help="scenarios to run, all without")
    parser.add_argument("--build", default=os.environ.get("BUILD_SCRIPT_BINARY"), help="the build-script binary")
    parser.add_argument("--kind", nargs="*", default=[], help="c-cpp, jvm, android, go")
    parser.add_argument("--slow", action="store_true", help="also the scenarios that take hours")
    parser.add_argument("--list", action="store_true", help="only list the scenarios")
    parser.add_argument("--device", help="serial of the device or emulator apps are started on, those steps are left out without")
    parser.add_argument("--device-only", action="store_true", help="only the scenarios that start apps on the device")
    arguments = parser.parse_args()

    if arguments.device_only and not arguments.device:
        parser.error("--device-only needs --device")

    scenarios = [Scenario(file.parent) for file in sorted(SCENARIOS.glob("*/*/scenario.toml"))]
    unknown = set(arguments.names) - {scenario.name for scenario in scenarios}
    if unknown:
        parser.error(f"no scenario {', '.join(sorted(unknown))}")

    chosen = [
        scenario for scenario in scenarios
        if (not arguments.names or scenario.name in arguments.names)
        and (not arguments.kind or scenario.kind in arguments.kind)
        and (arguments.names or scenario.runs_here(arguments.slow))
        and (not arguments.device_only or scenario.starts_apps())
    ]

    if arguments.list:
        for scenario in chosen:
            print(f"{scenario.kind:8} {scenario.name:48} {scenario.about}")
        return 0

    if not arguments.build:
        parser.error("--build names the build-script binary")
    build = str(Path(arguments.build).resolve())

    os.environ.setdefault("BUILD_SCRIPT_HOME", str(ROOT / ".home"))
    logs = ROOT / ".logs"
    remove_tree(logs)
    logs.mkdir()

    failed = []
    for scenario in chosen:
        print(f"{scenario.kind}/{scenario.name}: {scenario.about}", flush=True)
        if run(scenario, build, logs, arguments.device):
            failed.append(scenario.name)
        sys.stdout.flush()

    print(f"\n{len(chosen) - len(failed)} of {len(chosen)} scenarios passed" + (f", failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
