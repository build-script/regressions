#!/usr/bin/env python3
# Runs the regression scenarios against a build-script binary. A scenario is a directory with a
# scenario.toml: the repository and commit of its sources, if it has any, and the commands to run.
# The files in its project/ go on top of the sources, or are the project.
#
#   python3 run.py --build ../build/target/release/build-script            every scenario of this system
#   python3 run.py --build ... --kind c-cpp jvm                             the C and C++ and the JVM ones
#   python3 run.py --build ... cJSON new-kotlin                             these
#   python3 run.py --build ... --slow                                       with those that take hours
#
# BUILD_SCRIPT_HOME is .home/ unless it is set. Logs go to .logs/, the projects are built in .work/.
import argparse
import os
import re
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
    if step["again"] and ("Up to date" not in output or WORK_DONE.search(output)):
        return "not up to date"
    if step["arguments"][0] == "test" and not step["fails"] and "> Tests" not in output:
        return "no test summary"
    if step["arguments"][0] == "run":
        lines = [line for line in output.splitlines() if not (step["harmless"] and step["harmless"] in line)]
        if match := LINKAGE_ERRORS.search("\n".join(lines)):
            return match.group(0)
    return None


def run(scenario, build, logs):
    work = prepare(scenario)
    environment = dict(os.environ)
    extra = [path for path in scenario.config.get("path", []) if Path(path).is_dir()]
    environment["PATH"] = os.pathsep.join([*extra, environment["PATH"]])

    failures = 0
    for index, entry in enumerate(scenario.config["steps"], 1):
        step = step_of(entry)
        if SYSTEM not in step["platforms"]:
            continue

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
        seconds = round(time.monotonic() - started)
        last = next((line for line in reversed(output.splitlines()) if line.strip()), "")[:100]

        if problem is None:
            print(f"  ok    {step['label']} ({seconds}s) {last}")
            continue

        failures += 1
        print(f"  FAIL  {step['label']} ({seconds}s): {problem}, see {log.relative_to(ROOT)}")
        if IN_PIPELINE:
            print("::group::the end of the log")
            print("\n".join(output.splitlines()[-80:]))
            print("::endgroup::")

        # what follows needs this step
        break

    return failures


def main():
    parser = argparse.ArgumentParser(description="Runs the regression scenarios against a build-script binary")
    parser.add_argument("names", nargs="*", help="scenarios to run, all without")
    parser.add_argument("--build", default=os.environ.get("BUILD_SCRIPT_BINARY"), help="the build-script binary")
    parser.add_argument("--kind", nargs="*", default=[], help="c-cpp, jvm, android")
    parser.add_argument("--slow", action="store_true", help="also the scenarios that take hours")
    parser.add_argument("--list", action="store_true", help="only list the scenarios")
    arguments = parser.parse_args()

    scenarios = [Scenario(file.parent) for file in sorted(SCENARIOS.glob("*/*/scenario.toml"))]
    unknown = set(arguments.names) - {scenario.name for scenario in scenarios}
    if unknown:
        parser.error(f"no scenario {', '.join(sorted(unknown))}")

    chosen = [
        scenario for scenario in scenarios
        if (not arguments.names or scenario.name in arguments.names)
        and (not arguments.kind or scenario.kind in arguments.kind)
        and (arguments.names or scenario.runs_here(arguments.slow))
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
        if run(scenario, build, logs):
            failed.append(scenario.name)
        sys.stdout.flush()

    print(f"\n{len(chosen) - len(failed)} of {len(chosen)} scenarios passed" + (f", failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
