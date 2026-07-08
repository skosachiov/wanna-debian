#!/usr/bin/env bash
set -euo pipefail

debug=0

usage() { echo "Usage: $(basename "$0") [--debug] <pkg_a.deb> <pkg_b.deb>"; exit 1; }

[[ $# -ge 2 ]] || usage
if [[ "$1" == "--debug" ]]; then
    debug=1
    shift
fi
[[ $# -eq 2 ]] || usage
pkg_a=$(realpath "$1")
pkg_b=$(realpath "$2")
[[ -f "$pkg_a" ]] || { echo "ERROR: not a file: $pkg_a"; exit 1; }
[[ -f "$pkg_b" ]] || { echo "ERROR: not a file: $pkg_b"; exit 1; }

n_a=$(basename "$pkg_a")
n_b=$(basename "$pkg_b")

# Extract needed libraries and ABI symbols from a .deb
extract_info() {
    local deb="$1" tmpdir
    tmpdir=$(mktemp -d)
    dpkg-deb -x "$deb" "$tmpdir" >/dev/null 2>&1
    find "$tmpdir" -type f -exec file {} + 2>/dev/null \
        | awk -F: '/ELF/ {print $1}' \
        | sort -u \
        | while read -r elf; do
            readelf -d "$elf" 2>/dev/null | grep NEEDED || true
            if [[ "$elf" == *.so* ]]; then
                nm -D "$elf" 2>/dev/null | awk '{
                    if ($1 ~ /^[0-9a-fA-F]+$/) { $1="" }
                    gsub(/^ +/, "")
                    print
                }' || true
            fi
          done \
        | sort -u
    rm -rf "$tmpdir"
}

info_a=$(extract_info "$pkg_a")
info_b=$(extract_info "$pkg_b")

# Needed libraries comparison
needed_a=$(grep NEEDED <<< "$info_a" || true)
needed_b=$(grep NEEDED <<< "$info_b" || true)

need_diff=""
need_diff_out=""
if ! need_diff_out=$(diff <(echo "$needed_a") <(echo "$needed_b") 2>&1); then
    need_diff="NEEDED-LIBS:DIFFER"
fi

# ABI symbols comparison (nm -D on .so files, first column removed)
syms_a=$(grep -v NEEDED <<< "$info_a" | grep . || true)
syms_b=$(grep -v NEEDED <<< "$info_b" | grep . || true)
abi_diff=""
abi_diff_out=""
if ! abi_diff_out=$(diff <(echo "$syms_a") <(echo "$syms_b") 2>&1); then
    abi_diff="ABI:DIFFER"
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
    if (( debug )); then
        [[ -n "$need_diff" ]] && echo "--- NEEDED-LIBS diff ---"$'\n'"$need_diff_out"
        [[ -n "$abi_diff" ]] && echo "--- ABI-SYMBOLS diff ---"$'\n'"$abi_diff_out"
    fi
fi
