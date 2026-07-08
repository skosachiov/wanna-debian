#!/usr/bin/env bash
set -euo pipefail

usage() { echo "Usage: $(basename "$0") <pkg_a.deb> <pkg_b.deb>"; exit 1; }

[[ $# -eq 2 ]] || usage
pkg_a=$(realpath "$1")
pkg_b=$(realpath "$2")
[[ -f "$pkg_a" ]] || { echo "ERROR: not a file: $pkg_a"; exit 1; }
[[ -f "$pkg_b" ]] || { echo "ERROR: not a file: $pkg_b"; exit 1; }

n_a=$(basename "$pkg_a")
n_b=$(basename "$pkg_b")

# ABI check
abi_diff=""
if command -v abipkgdiff &>/dev/null; then
    abi_out=$(abipkgdiff --no-default-suppression "$pkg_a" "$pkg_b" 2>&1 || true)
    summary=$(echo "$abi_out" | grep -iE '^(  )?(Functions|Variables) changes summary' || true)
    if [[ -z "$summary" ]]; then
        abi_diff="ABI:DIFFER"
    else
        total=$(echo "$summary" | grep -oP '\d+(?= (Removed|Changed|Added))' | awk '{s+=$1} END {print s+0}')
        [[ "$total" -gt 0 ]] && abi_diff="ABI:DIFFER"
    fi
fi

# Needed libraries comparison
extract_needed() {
    local deb="$1" tmpdir
    tmpdir=$(mktemp -d)
    dpkg-deb -x "$deb" "$tmpdir" >/dev/null 2>&1
    find "$tmpdir" -type f -exec file {} + 2>/dev/null \
        | awk -F: '/ELF/ {print $1}' \
        | sort -u \
        | while read -r elf; do readelf -d "$elf" 2>/dev/null | grep NEEDED || true; done \
        | sort -u
    rm -rf "$tmpdir"
}

needed_a=$(extract_needed "$pkg_a")
needed_b=$(extract_needed "$pkg_b")

need_diff=""
if ! diff <(echo "$needed_a") <(echo "$needed_b") >/dev/null 2>&1; then
    need_diff="NEEDED-LIBS:DIFFER"
fi

# Result
diffs=()
[[ -n "$abi_diff" ]] && diffs+=("$abi_diff")
[[ -n "$need_diff" ]] && diffs+=("$need_diff")

if [[ ${#diffs[@]} -eq 0 ]]; then
    echo "$n_a $n_b OK"
else
    joined=$(IFS=' '; echo "${diffs[*]}")
    echo "$n_a $n_b $joined"
fi
