#!/usr/bin/env python3

import argparse
import os
import pathlib
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

SCRIPT_NAME = pathlib.Path(sys.argv[0]).name

BINARY_BUILD = "binary-amd64"
SOURCE_BUILD = "source"
# Corrected name is documented; the misspelled original is still honored.
ENV_INCOMPLETENESS = "INCOMPLETENESS"
ENV_INCOMPLETENESS_LEGACY = "INCOMPLETNESS"


def die(message):
    print(f"distrostatus: {message}", file=sys.stderr)
    sys.exit(1)


def prog(message, verbose):
    if verbose:
        print(f"distrostatus: {message}", file=sys.stderr)


def q(value):
    """Quote a value for safe interpolation into a shell command string."""
    return shlex.quote(str(value))


# ---------------------------------------------------------------------------
# path and setting resolution (flag > environment > built-in default)
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    root_dir: str
    meta_dir: str
    config_file: str
    dists_dir: str
    reports_dir: str
    dists_max: str
    incompleteness: str
    base_dist: str
    outdate_ref: str
    verbose: bool


def _env(name, legacy=None):
    """Environment value, preferring the corrected name over the legacy one."""
    if name in os.environ and os.environ[name] != "":
        return os.environ[name]
    if legacy and legacy in os.environ and os.environ[legacy] != "":
        return os.environ[legacy]
    return None


def resolve_settings(parsed):
    """Resolve every setting. `parsed` is the permissive pre-parse result
    (only flags that were explicitly given are non-None)."""
    g = lambda name: getattr(parsed, name, None)

    root_dir = g("root_dir") or _env("ROOT_DIR") or str(
        pathlib.Path(__file__).resolve().parent)
    meta_dir = g("meta_dir") or _env("META_DIR") or f"{root_dir}/metadata"
    config_file = g("config_file") or _env("CONFIG_FILE") or f"{meta_dir}/config.json"
    dists_dir = g("dists_dir") or _env("DISTS_DIR") or f"{meta_dir}/dists"
    reports_dir = g("reports_dir") or _env("REPORTS_DIR") or f"{root_dir}/reports"

    dists_max = g("dists_max") or _env("DISTS_MAX") or ""
    incompleteness = (g("incompleteness")
                      or _env(ENV_INCOMPLETENESS, ENV_INCOMPLETENESS_LEGACY)
                      or "1024")
    base_dist = g("base_dist") or _env("BASE_DIST") or "testing"
    outdate_ref = g("outdate_ref") or _env("OUTDATE_REF") or "debian_sources"

    return Settings(
        root_dir=root_dir, meta_dir=meta_dir, config_file=config_file,
        dists_dir=dists_dir, reports_dir=reports_dir, dists_max=dists_max,
        incompleteness=incompleteness, base_dist=base_dist,
        outdate_ref=outdate_ref, verbose=bool(g("verbose")))


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    """ArgumentParser that reports like the original `die()`: a
    `distrostatus: ` prefixed message on stderr and exit status 1, with the
    original's wording for the two option errors it can raise."""

    def error(self, message):
        if message.startswith("unrecognized arguments: "):
            opt = message.split(": ", 1)[1].split()[0]
            message = (f"unrecognized option '{opt}'. "
                       f"Run '{SCRIPT_NAME} --help' for usage.")
        elif message.startswith("argument ") and message.endswith(
                ": expected one argument"):
            opt = message[len("argument "):-len(": expected one argument")]
            message = (f"option '{opt}' requires a value. "
                       f"Run '{SCRIPT_NAME} --help' for usage.")
        die(message)


def _pre_parser():
    """Permissive first pass: collect only what was explicitly provided so
    defaults can be derived before the real help text is built. It must
    stay silent about errors; the real parser reports them."""

    class _Quiet(argparse.ArgumentParser):
        def error(self, message):        # never exit with a pre-parser message
            raise _PreParseError(message)

    p = _Quiet(add_help=False, argument_default=argparse.SUPPRESS,
               exit_on_error=False)
    p.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS)
    p.add_argument("--root-dir", dest="root_dir")
    p.add_argument("--meta-dir", dest="meta_dir")
    p.add_argument("--reports-dir", dest="reports_dir")
    p.add_argument("--config-file", dest="config_file")
    p.add_argument("--dists-dir", dest="dists_dir")
    p.add_argument("--dists-max", dest="dists_max")
    p.add_argument("--incompleteness", dest="incompleteness")
    p.add_argument("--base-dist", dest="base_dist")
    p.add_argument("--outdate-ref", dest="outdate_ref")
    return p


class _PreParseError(Exception):
    pass


def build_parser(s):
    """Real parser, with resolved defaults shown in the help text."""
    p = _Parser(
        prog=SCRIPT_NAME,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Analyzes distributions under\n"
            f"  {s.dists_dir}\n"
            "and writes a health report."),
        add_help=False)
    p.add_argument("--help", "-h", action="help",
                   help="Print this usage and exit")
    p.add_argument("--verbose", action="store_true",
                   default=s.verbose,
                   help=("Print progress to stderr: the current distribution "
                         "and each check as it begins"))
    p.add_argument("--root-dir", dest="root_dir", default=s.root_dir,
                   metavar="PATH",
                   help=("Project root (overrides ROOT_DIR; default: script "
                         f"directory) [{s.root_dir}]"))
    p.add_argument("--meta-dir", dest="meta_dir", default=s.meta_dir,
                   metavar="PATH",
                   help=("Path to the metadata mirror (overrides META_DIR; "
                         f"default: ROOT_DIR/metadata) [{s.meta_dir}]"))
    p.add_argument("--reports-dir", dest="reports_dir", default=s.reports_dir,
                   metavar="PATH",
                   help=("Where report.json and report.md are written "
                         "(overrides REPORTS_DIR; default: ROOT_DIR/reports) "
                         f"[{s.reports_dir}]"))
    p.add_argument("--config-file", dest="config_file", default=s.config_file,
                   metavar="PATH",
                   help=("Path to the mirror config (overrides CONFIG_FILE; "
                         f"default: META_DIR/config.json) [{s.config_file}]"))
    p.add_argument("--dists-dir", dest="dists_dir", default=s.dists_dir,
                   metavar="PATH",
                   help=("Path to the dists directory (overrides DISTS_DIR; "
                         f"default: META_DIR/dists) [{s.dists_dir}]"))
    p.add_argument("--dists-max", dest="dists_max", default=s.dists_max,
                   metavar="N",
                   help=("Cap the number of distributions processed in this "
                         "run (overrides DISTS_MAX; unset = process every "
                         "distribution)"))
    p.add_argument("--incompleteness", dest="incompleteness",
                   default=s.incompleteness, metavar="N",
                   help=("Binary-package threshold below which a non-incompleted "
                         "dist receives a background resolver-only input to "
                         "the dose checks; at or above it a non-incompleted dist "
                         "is checked with its own pool only (overrides "
                         f"INCOMPLETENESS; default: 1024) [{s.incompleteness}]"))
    p.add_argument("--base-dist", dest="base_dist", default=s.base_dist,
                   metavar="PATH",
                   help=("Base distribution whose pool is a background "
                         "resolver-only input to the dose checks (overrides "
                         f"BASE_DIST; default: testing) [{s.base_dist}]"))
    p.add_argument("--outdate-ref", dest="outdate_ref", default=s.outdate_ref,
                   metavar="PATH",
                   help=("Reference distribution the Outdate check compares "
                         "source packages against (overrides OUTDATE_REF; "
                         f"default: debian_sources) [{s.outdate_ref}]"))
    p.epilog = (
        "Environment (flags override these; values fall back to "
        "built-in defaults):\n"
        "  ROOT_DIR      Root of the project (default: script directory)\n"
        "  META_DIR      Path to the metadata mirror (default: ROOT_DIR/metadata)\n"
        "  REPORTS_DIR   Where report.json and report.md are written "
        "(default: ROOT_DIR/reports)\n"
        "  CONFIG_FILE   Path to the mirror config (default: META_DIR/config.json)\n"
        "  DISTS_DIR     Path to the dists directory (default: META_DIR/dists)\n"
        "  DISTS_MAX     Cap the number of distributions processed in this run\n"
        "                (unset = process every distribution)\n"
        "  INCOMPLETENESS Binary-package threshold below which a non-incompleted dist\n"
        "                receives a background resolver-only input to the dose\n"
        "                checks; at or above it a non-incompleted dist is checked\n"
        "                with its own pool only (default: 1024)\n"
        "  BASE_DIST     Base distribution whose pool is a background\n"
        "                resolver-only input to the dose checks (default: testing)\n"
        "  OUTDATE_REF   Reference distribution the Outdate check compares\n"
        "                source packages against (default: debian_sources)\n"
        "\n"
        "Required tools: sort, wc, jq, paste, grep (with -P), find, stat,\n"
        "date, awk, uniq, sed, cut, head, distrotracker, dose-debcheck,\n"
        "dose-builddebcheck\n"
        "\n"
        f"Reports:\n"
        "  $REPORTS_DIR/<dist>.json   Per-distribution report, one per processed dist\n"
        "  $REPORTS_DIR/report.json   Combined machine-readable result (aggregated from\n"
        "                              the per-dist files)\n"
        "  $REPORTS_DIR/report.md     Combined human-readable summary (same data)\n"
        "\n"
        "A distribution is (re)processed only when its newest "
        "Packages.json/Sources.json\n"
        "index file is newer than its existing per-dist report, or when no "
        "per-dist\n"
        "report exists yet. Unchanged distributions are skipped and their "
        "existing\n"
        "report file is reused.\n"
    )
    return p


def parse_args(argv):
    """Two-phase parse: derive defaults from a permissive pass, then parse
    for real so --help shows resolved paths. The permissive pass must never
    fail on malformed input - the real parser owns all diagnostics."""
    try:
        pre = _pre_parser().parse_known_args(argv)[0]
    except (_PreParseError, argparse.ArgumentError, SystemExit):
        # Malformed value for a taking-value flag: let the real parser
        # produce the error against its resolved help/defaults.
        pre = argparse.Namespace()
    settings = resolve_settings(pre)
    parser = build_parser(settings)
    args = parser.parse_args(argv)
    return parser, args


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

REQUIRED_TOOLS = [
    "jq", "awk", "sort", "uniq", "paste", "wc", "sed", "cut", "head",
    "find", "stat", "date",
    "distrotracker", "dose-debcheck", "dose-builddebcheck",
]


def _feature_ok(probe):
    """Run a feature probe; exit 0 or 1 means supported, anything else not."""
    r = subprocess.run(["bash", "-c", probe], capture_output=True)
    return r.returncode in (0, 1)


def check_tools():
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]

    unsupported = []
    if shutil.which("grep") and not _feature_ok("printf a | grep -P a >/dev/null"):
        unsupported.append("grep -P (PCRE matching)")
    if shutil.which("find") and not _feature_ok(
            "find /dev/null -printf '%T@\\n' >/dev/null"):
        unsupported.append("find -printf")
    if shutil.which("stat") and not _feature_ok("stat -c %Y /dev/null >/dev/null"):
        unsupported.append("stat -c")
    if shutil.which("date") and not _feature_ok("date -u -d @0 +%s >/dev/null"):
        unsupported.append("date -d @")

    problems = []
    if missing:
        problems.append("missing required tool(s): " + ", ".join(missing))
    if unsupported:
        problems.append("unsupported required feature(s): " + ", ".join(unsupported))
    if problems:
        die(". ".join(problems) + ". Please install them and re-run.")


# ---------------------------------------------------------------------------
# runner: external commands stay external
# ---------------------------------------------------------------------------

def pipeline(text, check=True):
    """Run a shell pipeline. Always under `bash -o pipefail -c`, matching the
    original's `set -o pipefail` so a failed stage aborts instead of yielding
    corrupted output. `check=False` is for the original's best-effort
    pipelines (`|| true`)."""
    r = subprocess.run(["bash", "-o", "pipefail", "-c", text],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"pipeline failed (exit {r.returncode}): {text}")
    return r


def argv(cmd, stdout=None, check=True):
    """Run a single external command without a shell."""
    r = subprocess.run(cmd, stdout=stdout, capture_output=True)
    if check and r.returncode != 0:
        die(f"command failed (exit {r.returncode}): {' '.join(cmd)}")
    return r


# ---------------------------------------------------------------------------
# config and discovery
# ---------------------------------------------------------------------------

@dataclass
class Config:
    builds: list


def load_config(config_file):
    r = subprocess.run(["jq", "-r", ".builds[]", config_file],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(f"could not read builds from {config_file}: {r.stderr.strip()}")
    return Config(builds=[b for b in r.stdout.splitlines() if b])


def has_build(config, build):
    return build in config.builds


def is_incompleted_dist(name):
    # Match prefix-reponame-suffix or prefix_reponame_suffix patterns
    if "-" in name:
        parts = name.split("-")
        if len(parts) == 3:
            # Any 3-part form with separators is considered a incompleted pattern variant
            # and we look for reponame as middle component typically
            return True
    if "_" in name:
        parts = name.split("_")
        if len(parts) == 3:
            return True
    # Also handle 2-part forms that might be prefix-reponame or prefix_reponame
    # where first is prefix indicating incompleted? Or just check common forms
    if "-" in name:
        parts = name.split("-")
        if len(parts) == 2:
            # Could be prefix-reponame style; treat as incompleted pattern variant
            return True
    if "_" in name:
        parts = name.split("_")
        if len(parts) == 2:
            return True
    return False


def incompleted_parent_of(name):
    if not is_incompleted_dist(name):
        return None
    # Try dash split for prefix-reponame-suffix or prefix-reponame
    if "-" in name:
        parts = name.split("-")
        if len(parts) == 3:
            # prefix-reponame-suffix -> reponame is middle
            return parts[1]
        if len(parts) == 2:
            # prefix-reponame -> reponame is second part? Or first?
            # "incompleted_bookworm" style was prefix_reponame in old terms; but without using tokens,
            # try to extract reponame - often it's the second component
            # Prefer the component that is likely the base name (more common as directory name)
            # Try second as reponame
            return parts[1]
    # Try underscore split
    if "_" in name:
        parts = name.split("_")
        if len(parts) == 3:
            return parts[1]
        if len(parts) == 2:
            return parts[1]
    return None


def newest_index_mtime(index_dir):
    """Newest Packages.json/Sources.json mtime, as epoch seconds, or None."""
    text = (f"find {q(index_dir)} -type f "
            f"\\( -name Packages.json -o -name Sources.json \\) "
            f"-printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -n1 "
            f"| sed 's/^[^ ]* //'")
    r = pipeline(text, check=False)
    newest = r.stdout.strip()
    if not newest:
        return None
    s = argv(["stat", "-c", "%Y", newest], check=False)
    if s.returncode != 0:
        return None
    return int(s.stdout.strip())


def newest_compressed_index_mtime(index_dir):
    """Newest compressed index mtime, falling back to the directory mtime."""
    text = (f"find {q(index_dir)} -type f "
            f"\\( -name Packages.gz -o -name Sources.gz "
            f"-o -name Packages.xz -o -name Sources.xz \\) "
            f"-printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -n1 "
            f"| sed 's/^[^ ]* //'")
    r = pipeline(text, check=False)
    newest = r.stdout.strip()
    if newest:
        s = argv(["stat", "-c", "%Y", newest], check=False)
        if s.returncode == 0:
            return int(s.stdout.strip())
    if not pathlib.Path(index_dir).is_dir():
        return None
    s = argv(["stat", "-c", "%Y", index_dir], check=False)
    return int(s.stdout.strip()) if s.returncode == 0 else None


def incompleted_parent_map(dists_dir):
    mapping = {}
    root = pathlib.Path(dists_dir)
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if not d.is_dir():
            continue
        name = d.name
        parent = incompleted_parent_of(name)
        if parent and (root / parent).is_dir():
            mapping[name] = parent
    return mapping


def ordered_dist_dirs(dists_dir):
    """Directories under dists_dir, newest compressed index first, name
    tie-break, matching the original's `sort -t'|' -k1,1nr -k2,2`."""
    root = pathlib.Path(dists_dir)
    entries = []
    for d in root.iterdir() if root.is_dir() else []:
        if not d.is_dir():
            continue
        t = newest_compressed_index_mtime(str(d))
        entries.append((0 if t is None else t, d.name, str(d)))
    if not entries:
        return []
    text = "".join(f"{t:010d}|{name}|{path}\n" for t, name, path in entries)
    r = pipeline(f"printf %s {q(text)} | sort -t'|' -k1,1nr -k2,2 | cut -d'|' -f3-",
                 check=False)
    return [line for line in r.stdout.splitlines() if line]


def needs_reprocess(reports_dir, dist, dist_dir, config, incompleteness):
    report = pathlib.Path(reports_dir) / f"{dist}.json"
    if not report.is_file():
        return True

    newest = newest_index_mtime(dist_dir)
    if newest is None:
        return False
    report_mtime = int(argv(["stat", "-c", "%Y", str(report)]).stdout.strip())
    if newest > report_mtime:
        return True

    if has_build(config, BINARY_BUILD):
        check = subprocess.run(["jq", "-e", ".dose != null", str(report)],
                               capture_output=True)
        if check.returncode != 0:
            return True
    return False


# ---------------------------------------------------------------------------
# per-distribution checks
# ---------------------------------------------------------------------------

@dataclass
class DistRecord:
    dist: str
    binary_count: int = 0
    source_count: int = 0
    nosource_list: list = field(default_factory=list)
    nobinary_list: list = field(default_factory=list)
    noarch_list: list = field(default_factory=list)
    outdate_list: list = field(default_factory=list)
    dose_debcheck_list: list = field(default_factory=list)
    dose_builddebcheck_list: list = field(default_factory=list)
    dose_tested: bool = False
    health: str = ""


def run_count(rec, config, dist):
    if has_build(config, BINARY_BUILD):
        text = (f"distrotracker --hold --all -d {q(dist)} -b {q(BINARY_BUILD)} "
                f"| jq -c -r '.[] | \"\\(.package)=\\(.version)\"' | wc -l")
        rec.binary_count = int(pipeline(text).stdout.strip() or "0")
    if has_build(config, SOURCE_BUILD):
        text = (f"distrotracker --hold --all -d {q(dist)} -b {q(SOURCE_BUILD)} "
                f"| jq -c -r '.[] | \"\\(.package)=\\(.version)\"' | wc -l")
        rec.source_count = int(pipeline(text).stdout.strip() or "0")


def _read_lines(path):
    p = pathlib.Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return p.read_text().splitlines()
    return []


def run_nosource(rec, config, dist, scratch):
    if has_build(config, BINARY_BUILD) and has_build(config, SOURCE_BUILD) \
            and rec.binary_count > 0:
        tmp = f"{scratch}/{dist}.nosource"
        text = (
            f"distrotracker --hold --all -d {q(dist)} -b {q(BINARY_BUILD)} "
            f"| jq -c -r '.[] | \"\\(.source) (= \\(.source_version))\"' "
            f"| sort -u "
            f"| distrotracker --hold --find --source --dist {q(dist)} "
            f"--build {q(SOURCE_BUILD)} 2>&1 "
            f"| grep -P \"WARNING Can not find|WARNING Package versions\" "
            f"| grep -oP ': \\K.*' > {q(tmp)} || true")
        pipeline(text, check=False)
        rec.nosource_list = _read_lines(tmp)


def run_nobinary(rec, config, dist, scratch):
    if has_build(config, SOURCE_BUILD) and has_build(config, BINARY_BUILD) \
            and rec.source_count > 0:
        tmp = f"{scratch}/{dist}.nobinary"
        text = (
            f"distrotracker --hold --all -d {q(dist)} -b {q(SOURCE_BUILD)} "
            f"| jq -c -r '.[] | \"\\(.package) (= \\(.version))\"' "
            f"| sort -u "
            f"| distrotracker --hold --find --source --dist {q(dist)} "
            f"--build {q(BINARY_BUILD)} 2>&1 "
            f"| grep -P \"WARNING Can not find|WARNING Package versions\" "
            f"| grep -oP ': \\K.*' > {q(tmp)} || true")
        pipeline(text, check=False)
        rec.nobinary_list = _read_lines(tmp)


def run_noarch(rec, config, dist, scratch):
    if has_build(config, BINARY_BUILD) and rec.binary_count > 0:
        s1 = f"{scratch}/{dist}.na_stage1"
        s2 = f"{scratch}/{dist}.na_stage2"
        s3 = f"{scratch}/{dist}.na_stage3"
        tmp = f"{scratch}/{dist}.noarch"
        pipeline(
            f"distrotracker --hold --all -d {q(dist)} -b {q(BINARY_BUILD)} "
            f"| jq -c -r '.[] | \"\\(.source) (= \\(.source_version))\"' "
            f"| sort -u > {q(s1)} || true", check=False)
        pipeline(
            f"distrotracker --hold --find --source --dist {q(dist)} "
            f"< {q(s1)} 2>/dev/null "
            f"| jq -c -r '.[] | select(.build==\"source\") | select(.arch | "
            f"contains(\"all\") and (contains(\"any\") or contains(\"linux-any\") "
            f"or contains(\"amd64\"))) | \"\\(.source) (= \\(.source_version))\"' "
            f"| sort -u > {q(s2)} || true", check=False)
        pipeline(
            f"distrotracker --hold --find --source --dist {q(dist)} "
            f"--build {q(BINARY_BUILD)} < {q(s2)} 2>/dev/null "
            f"| jq -r '.[] | \"\\(.source) \\(.arch)\"' | sort -u "
            f"> {q(s3)} || true", check=False)
        pipeline(
            f"awk '{{print $1}}' {q(s3)} | uniq -c | awk '$1==1 {{print $2}}' "
            f"> {q(tmp)} || true", check=False)
        rec.noarch_list = _read_lines(tmp)


def run_outdate(rec, config, dist, scratch, outdate_ref):
    if has_build(config, SOURCE_BUILD) and rec.source_count > 0:
        tmp = f"{scratch}/{dist}.outdate"
        pipeline(
            f"distrotracker --hold --all -d {q(dist)} -b {q(SOURCE_BUILD)} --latest "
            f"| jq -c -r '.[] | \"\\(.source) (>> \\(.source_version))\"' | sort -u "
            f"| distrotracker --hold --find --dist {q(outdate_ref)} "
            f"--build {q(SOURCE_BUILD)} --latest 2>/dev/null "
            f"| jq -c -r '.[] | \"\\(.source)=\\(.source_version)\"' | sort -u "
            f"> {q(tmp)} || true", check=False)
        rec.outdate_list = _read_lines(tmp)


def run_dose(rec, config, dist, dist_dir, scratch, dists_dir,
             base_dist, incompleteness, incompleted_parent):
    if not has_build(config, BINARY_BUILD):
        return
    rec.dose_tested = True
    bootstrap_p = f"{scratch}/{dist}.bootstrap_Packages"
    bootstrap_s = f"{scratch}/{dist}.bootstrap_Sources"
    pipeline(f"find {q(dist_dir)} -path "
             f"\"*{BINARY_BUILD}/Packages\" -type f -exec cat {{}} + "
             f"> {q(bootstrap_p)} || true", check=False)
    pipeline(f"find {q(dist_dir)} -path "
             f"\"*{SOURCE_BUILD}/Sources\" -type f -exec cat {{}} + "
             f"> {q(bootstrap_s)} || true", check=False)

    bg_bootstrap_p = ""
    bg_bootstrap_s = ""
    bg_start = []
    if is_incompleted_dist(dist):
        parent = incompleted_parent.get(dist, "")
        if parent and (pathlib.Path(dists_dir) / parent).is_dir():
            bg_start.append(f"{dists_dir}/{parent}/")
    elif rec.binary_count < int(incompleteness):
        if base_dist and (pathlib.Path(dists_dir) / base_dist).is_dir():
            bg_start.append(f"{dists_dir}/{base_dist}/")
    if bg_start:
        bg_bootstrap_p = f"{scratch}/{dist}.bootstrap_Packages.bg"
        bg_bootstrap_s = f"{scratch}/{dist}.bootstrap_Sources.bg"
        bg = " ".join(q(b) for b in bg_start)
        pipeline(f"find {bg} -path \"*{BINARY_BUILD}/Packages\" -type f "
                 f"-exec cat {{}} + > {q(bg_bootstrap_p)} || true", check=False)
        pipeline(f"find {bg} -path \"*{SOURCE_BUILD}/Sources\" -type f "
                 f"-exec cat {{}} + > {q(bg_bootstrap_s)} || true", check=False)

    debcheck_args = ["--latest", "1", "--deb-native-arch=amd64", "-e",
                     "-f", bootstrap_p]
    if bg_bootstrap_p and pathlib.Path(bg_bootstrap_p).is_file() \
            and pathlib.Path(bg_bootstrap_p).stat().st_size > 0:
        debcheck_args.append(f"--bg={bg_bootstrap_p}")
    if pathlib.Path(bootstrap_p).is_file() and pathlib.Path(bootstrap_p).stat().st_size > 0:
        tmp = f"{scratch}/{dist}.dose_debcheck"
        args = " ".join(q(a) for a in debcheck_args)
        pipeline(
            f"dose-debcheck {args} 2>/dev/null "
            f"| grep -P -A 5 \"^\\s{{5}}pkg1?:\" "
            f"| grep -P \"^\\s{{6}}(unsat-|package:)\" "
            f"| paste - - | sort | uniq -c > {q(tmp)} || true", check=False)
        rec.dose_debcheck_list = _read_lines(tmp)

    if bg_start:
        build_p = f"{scratch}/{dist}.bootstrap_Packages.build"
        build_s = f"{scratch}/{dist}.bootstrap_Sources.build"
        pipeline(f"cat {q(bootstrap_p)} > {q(build_p)} || true", check=False)
        if pathlib.Path(bg_bootstrap_p).is_file() and \
                pathlib.Path(bg_bootstrap_p).stat().st_size > 0:
            pipeline(f"cat {q(bg_bootstrap_p)} >> {q(build_p)} || true", check=False)
        pipeline(f"cat {q(bootstrap_s)} > {q(build_s)} || true", check=False)
        if pathlib.Path(bg_bootstrap_s).is_file() and \
                pathlib.Path(bg_bootstrap_s).stat().st_size > 0:
            pipeline(f"cat {q(bg_bootstrap_s)} >> {q(build_s)} || true", check=False)
    else:
        build_p = bootstrap_p
        build_s = bootstrap_s

    bp_ok = pathlib.Path(build_p).is_file() and pathlib.Path(build_p).stat().st_size > 0
    bs_ok = pathlib.Path(build_s).is_file() and pathlib.Path(build_s).stat().st_size > 0
    if bp_ok and bs_ok:
        tmp = f"{scratch}/{dist}.dose_builddebcheck"
        pipeline(
            f"dose-builddebcheck --latest 1 --deb-native-arch=amd64 -e "
            f"-f {q(build_p)} {q(build_s)} 2>/dev/null "
            f"| grep -P -A 5 \"^\\s{{5}}pkg1?:\" "
            f"| grep -P \"^\\s{{6}}(unsat-|package:)\" "
            f"| paste - - | sort | uniq -c > {q(tmp)} || true", check=False)
        rec.dose_builddebcheck_list = _read_lines(tmp)


# ---------------------------------------------------------------------------
# report entry
# ---------------------------------------------------------------------------

HEALTH_DEF = (pathlib.Path(__file__).resolve().parent
              / "tests" / "golden" / "jq" / "health_def.jq").read_text()
HEALTH_BODY = (pathlib.Path(__file__).resolve().parent
               / "tests" / "golden" / "jq" / "health_body.jq").read_text()
DOSE_ASSEMBLER = (pathlib.Path(__file__).resolve().parent
                  / "tests" / "golden" / "jq" / "dose_assembler.jq").read_text()
DOSE_MUTATE_DEBCHECK = (pathlib.Path(__file__).resolve().parent
                        / "tests" / "golden" / "jq"
                        / "dose_mutate_debcheck.jq").read_text()
DOSE_MUTATE_BUILDDEBCHECK = (pathlib.Path(__file__).resolve().parent
                             / "tests" / "golden" / "jq"
                             / "dose_mutate_builddebcheck.jq").read_text()
ENTRY_PROGRAM = (pathlib.Path(__file__).resolve().parent
                 / "tests" / "golden" / "jq" / "entry_program.jq").read_text()
SUMMARY_BODY = (pathlib.Path(__file__).resolve().parent
                / "tests" / "golden" / "jq" / "summary_body.jq").read_text()


def _jq_list_file(scratch, dist, name, values):
    """printf each value | jq -R select | jq -s -c .  -> <scratch>/<dist>.<name>.json"""
    dest = f"{scratch}/{dist}.{name}.json"
    stdin = "".join(f"{v}\n" for v in values)
    r1 = subprocess.run(["jq", "-R", "select(length>0)"],
                        input=stdin, capture_output=True, text=True)
    r2 = subprocess.run(["jq", "-s", "-c", "."],
                        input=r1.stdout, capture_output=True, text=True, check=True)
    pathlib.Path(dest).write_text(r2.stdout)
    return dest


def _build_dose_json(rec, scratch, dist):
    dest = f"{scratch}/{dist}.dose.json"
    if rec.dose_tested:
        stdin = ("".join(f"{v}\n" for v in rec.dose_debcheck_list)
                 + "\n--\n"
                 + "".join(f"{v}\n" for v in rec.dose_builddebcheck_list))
        r = subprocess.run(
            ["jq", "-Rs", DOSE_ASSEMBLER],
            input=stdin, capture_output=True, text=True, check=True)
        pathlib.Path(dest).write_text(r.stdout)
    else:
        pathlib.Path(dest).write_text("null\n")
    return dest


def _mutate_dose(dest, mutation):
    p = pathlib.Path(dest)
    if not p.is_file() or p.stat().st_size == 0:
        return
    jqtype = subprocess.run(["jq", "-r", "type", dest],
                            capture_output=True, text=True)
    if jqtype.stdout.strip() == "null":
        return
    r = subprocess.run(["jq", mutation, dest], capture_output=True, text=True, check=True)
    tmp = f"{dest}.tmp"
    pathlib.Path(tmp).write_text(r.stdout)
    argv(["mv", tmp, dest])


def build_health(rec, scratch, dist):
    dose_file = f"{scratch}/{dist}.dose.json"
    cmd = ["jq", "-c",
           "--argjson", "binary", str(rec.binary_count),
           "--argjson", "source", str(rec.source_count),
           "--argjson", "nosource", str(len(rec.nosource_list)),
           "--argjson", "nobinary", str(rec._nobinary_count),
           "--argjson", "noarch", str(rec._noarch_count),
           "--argjson", "outdate", str(rec._outdate_count),
           HEALTH_DEF + "\n      " + HEALTH_BODY + " | health_marker"]
    stdin = pathlib.Path(dose_file).read_text() if pathlib.Path(dose_file).is_file() else ""
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def build_report_entry(rec, config, args, scratch, dist, dist_dir,
                       compact_date, commit_hash):
    # sentinel counts: checks that cannot apply are -1, not 0
    if rec.source_count == 0:
        rec._nobinary_count = -1
        rec._noarch_count = -1
        rec._outdate_count = -1
    else:
        rec._nobinary_count = len(rec.nobinary_list)
        rec._noarch_count = len(rec.noarch_list)
        rec._outdate_count = len(rec.outdate_list)
    rec._nosource_count = -1 if rec.binary_count == 0 else len(rec.nosource_list)

    _jq_list_file(scratch, dist, "nobinary", rec.nobinary_list)
    _jq_list_file(scratch, dist, "noarch", rec.noarch_list)
    _jq_list_file(scratch, dist, "outdate", rec.outdate_list)
    dose_file = _build_dose_json(rec, scratch, dist)

    if rec.source_count == 0:
        _mutate_dose(dose_file, DOSE_MUTATE_BUILDDEBCHECK)
    if rec.binary_count == 0 and not (
            pathlib.Path(f"{scratch}/{dist}.bootstrap_Packages").is_file()
            and pathlib.Path(f"{scratch}/{dist}.bootstrap_Packages").stat().st_size > 0):
        _mutate_dose(dose_file, DOSE_MUTATE_DEBCHECK)

    health = build_health(rec, scratch, dist)
    rec.health = health

    pm = newest_compressed_index_mtime(dist_dir)
    pm_arg = "" if pm is None else str(pm)

    nosource_stdin = "".join(f"{v}\n" for v in rec.nosource_list)
    r1 = subprocess.run(["jq", "-R", "select(length>0)"],
                        input=nosource_stdin, capture_output=True, text=True)

    cmd = ["jq", "-s",
           "--slurpfile", "nobin", f"{scratch}/{dist}.nobinary.json",
           "--slurpfile", "na", f"{scratch}/{dist}.noarch.json",
           "--slurpfile", "outd", f"{scratch}/{dist}.outdate.json",
           "--slurpfile", "dose", dose_file,
           "--arg", "dist", dist,
           "--arg", "runDate", compact_date,
           "--arg", "commitHash", commit_hash,
           "--arg", "packagesCompMtime", pm_arg,
           "--argjson", "binary", str(rec.binary_count),
           "--argjson", "source", str(rec.source_count),
           "--argjson", "nosource", str(rec._nosource_count),
           "--argjson", "nobinary", str(rec._nobinary_count),
           "--argjson", "noarch", str(rec._noarch_count),
           "--argjson", "outdate", str(rec._outdate_count),
           "--argjson", "health", health,
           ENTRY_PROGRAM]
    r = subprocess.run(cmd, input=r1.stdout, capture_output=True, text=True, check=True)
    pathlib.Path(f"{args.reports_dir}/{dist}.json").write_text(r.stdout)


# ---------------------------------------------------------------------------
# aggregation and markdown
# ---------------------------------------------------------------------------

def _per_dist_files(reports_dir):
    root = pathlib.Path(reports_dir)
    files = []
    for f in sorted(root.iterdir()) if root.is_dir() else []:
        if not f.is_file() or f.name == "report.json" or f.suffix != ".json":
            continue
        files.append(str(f))
    return files


def aggregate(reports_dir, generated_at, compact_date, commit_hash):
    files = _per_dist_files(reports_dir)
    dist_count = len(files)
    stdin = ""
    for f in files:
        stdin += pathlib.Path(f).read_text()
    body = SUMMARY_BODY
    cmd = ["jq", "-s",
           "--arg", "generatedAt", generated_at,
           "--arg", "runDate", compact_date,
           "--arg", "commitHash", commit_hash,
           "--argjson", "count", str(dist_count),
           HEALTH_DEF + "\n        " + body]
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=True)
    pathlib.Path(f"{reports_dir}/report.json").write_text(r.stdout)


def _md_order(reports_dir):
    files = _per_dist_files(reports_dir)
    rows = []
    for f in files:
        name = subprocess.run(["jq", "-r", ".dist", f],
                              capture_output=True, text=True).stdout.strip()
        t = subprocess.run(["jq", "-r", ".packages_compressed_mtime", f],
                           capture_output=True, text=True).stdout.strip()
        if not t or t == "null":
            t = "0000000000"
        rows.append((t, name, f))
    text = "".join(f"{t}|{name}|{f}\n" for t, name, f in rows)
    if not text:
        return []
    r = pipeline(f"printf %s {q(text)} | sort -t'|' -k1,1nr -k2,2 | cut -d'|' -f3-",
                 check=False)
    return [line for line in r.stdout.splitlines() if line]


def write_markdown(reports_dir, generated_at, compact_date, commit_hash, dist_count):
    lines = [
        "# Distribution Health Report", "",
        f"Generated: {generated_at} ({compact_date})",
        f"Commit: {commit_hash or 'unknown'}",
        f"Distributions analyzed: {dist_count}", "",
        "## Summary", "",
        "| Packages-mtime | Distribution | Binary | Source | No-source | "
        "No-binary | No-arch | Outdate | Dose-deb | Dose-build | Health |",
        "|----------------|--------------|--------|--------|-----------|"
        "-----------|---------|---------|----------|------------|--------|",
    ]
    for f in _md_order(reports_dir):
        def jqr(prog):
            return subprocess.run(["jq", "-r", prog, f],
                                  capture_output=True, text=True).stdout.strip()
        name = jqr(".dist")
        pm_raw = jqr(".packages_compressed_mtime")
        if pm_raw and pm_raw != "null":
            d = subprocess.run(["date", "-u", "-d", f"@{pm_raw}", "+%Y-%m-%d %H:%M"],
                               capture_output=True, text=True)
            pm = d.stdout.strip() if d.returncode == 0 else ""
        else:
            pm = ""
        b = jqr(".binary")
        s = jqr(".source")
        ns = jqr(".nosource_count")
        nb = jqr(".nobinary_count")
        na = jqr(".noarch_count")
        od = jqr(".outdate.count")
        dd = jqr('if .dose == null then "-" else (.dose.debcheck_count|tostring) end')
        db = jqr('if .dose == null then "-" else (.dose.builddebcheck_count|tostring) end')
        h = subprocess.run(
            ["jq", "-r", HEALTH_DEF + "\n         health_marker", f],
            capture_output=True, text=True).stdout.strip()
        lines.append(
            f"| {pm} | [{name}](./{name}.json) | {b} | {s} | {ns} | {nb} | "
            f"{na} | {od} | {dd} | {db} | {h} |")
    pathlib.Path(f"{reports_dir}/report.md").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser, args = parse_args(argv)
    check_tools()
    if not pathlib.Path(args.config_file).is_file():
        die(f"config file not found: {args.config_file}")
    if not pathlib.Path(args.dists_dir).is_dir():
        die(f"dists directory not found: {args.dists_dir}")

    config = load_config(args.config_file)

    pathlib.Path(args.reports_dir).mkdir(parents=True, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="disto_")

    def cleanup(*_):
        shutil.rmtree(scratch, ignore_errors=True)

    def on_term(signum, frame):
        raise SystemExit(1)

    old_term = signal.signal(signal.SIGTERM, on_term)
    try:
        generated_at = subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
                                      capture_output=True, text=True).stdout.strip()
        compact_date = generated_at[:4] + generated_at[5:7] + generated_at[8:10]
        git = subprocess.run(["git", "-C", args.root_dir, "rev-parse", "HEAD"],
                             capture_output=True, text=True)
        commit_hash = git.stdout.strip() if git.returncode == 0 else ""

        incompleted_parent = incompleted_parent_map(args.dists_dir)
        dist_dirs = ordered_dist_dirs(args.dists_dir)

        dists_max = int(args.dists_max) if args.dists_max != "" else None

        processed = 0
        for dist_dir in dist_dirs:
            dist = pathlib.Path(dist_dir).name
            if not needs_reprocess(args.reports_dir, dist, dist_dir, config,
                                   args.incompleteness):
                prog(f"skipping {dist} (report is current)", args.verbose)
                continue
            if dists_max is not None and processed >= dists_max:
                break
            processed += 1

            prog(f"processing dist {dist}", args.verbose)
            rec = DistRecord(dist=dist)
            prog(f"running count on {dist}", args.verbose)
            run_count(rec, config, dist)
            prog(f"running no-source on {dist}", args.verbose)
            run_nosource(rec, config, dist, scratch)
            prog(f"running no-binary on {dist}", args.verbose)
            run_nobinary(rec, config, dist, scratch)
            prog(f"running no-arch on {dist}", args.verbose)
            run_noarch(rec, config, dist, scratch)
            prog(f"running outdate on {dist}", args.verbose)
            run_outdate(rec, config, dist, scratch, args.outdate_ref)
            prog(f"running dose on {dist}", args.verbose)
            run_dose(rec, config, dist, dist_dir, scratch, args.dists_dir,
                     args.base_dist, args.incompleteness, incompleted_parent)
            prog(f"building report entry on {dist}", args.verbose)
            build_report_entry(rec, config, args, scratch, dist, dist_dir,
                               compact_date, commit_hash)
            pipeline(f"rm -rf {q(scratch)}/{q(dist)}.*", check=False)

        files = _per_dist_files(args.reports_dir)
        dist_count = len(files)
        aggregate(args.reports_dir, generated_at, compact_date, commit_hash)
        write_markdown(args.reports_dir, generated_at, compact_date,
                       commit_hash, dist_count)
    finally:
        cleanup()
        signal.signal(signal.SIGTERM, old_term)

    print(f"distrostatus: analyzed {dist_count} distributions; report written "
          f"to {args.reports_dir} (report.json, report.md)")
    return 0


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
