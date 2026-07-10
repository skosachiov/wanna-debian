#!/usr/bin/env bash
set -euo pipefail

debug=0
tmpfiles=()

cleanup() {
    [[ ${#tmpfiles[@]} -gt 0 ]] && rm -f "${tmpfiles[@]}"
}
trap cleanup EXIT INT TERM HUP

usage() { echo "Usage: $(basename "$0") [--debug] <pkg_a.deb|url> <pkg_b.deb|url>"; exit 1; }

[[ $# -ge 2 ]] || usage
if [[ "$1" == "--debug" ]]; then
    debug=1
    shift
fi
[[ $# -eq 2 ]] || usage

resolve_pkg() {
    local arg="$1"
    if [[ "$arg" == http://* || "$arg" == https://* ]]; then
        local name=$(basename "$arg")
        local path="/tmp/$name"
        if command -v wget &>/dev/null; then
            wget -qO "$path" "$arg"
        else
            curl -sLo "$path" "$arg"
        fi
        tmpfiles+=("$path")
        echo "$path"
    else
        realpath "$arg"
    fi
}

pkg_a=$(resolve_pkg "$1")
pkg_b=$(resolve_pkg "$2")
[[ -f "$pkg_a" ]] || { echo "ERROR: not a file: $pkg_a"; exit 1; }
[[ -f "$pkg_b" ]] || { echo "ERROR: not a file: $pkg_b"; exit 1; }

n_a=$(basename "$pkg_a")
n_b=$(basename "$pkg_b")

extract_info() {
    local deb="$1" tmpdir
    tmpdir=$(mktemp -d)
    dpkg-deb -x "$deb" "$tmpdir" >/dev/null 2>&1

    find "$tmpdir" -type f -exec file {} + 2>/dev/null \
        | awk -F: '/ELF/ {print $1}' \
        | while read -r elf; do
            local rel_path="${elf#$tmpdir/}"

            # NEEDED and SONAME (optional: strip path to library name only)
            readelf -d "$elf" 2>/dev/null | awk -v p="$rel_path" '/SONAME/ {print "SONAME:", $NF}'
            readelf -d "$elf" 2>/dev/null | awk -v p="$rel_path" '/NEEDED/ {print "NEEDED:", $NF}'

            # Version definitions (keep as is – these are rarely used for ABI checks)
            readelf -V "$elf" 2>/dev/null | awk -v p="$rel_path" '/File:/{f=$5} /  Name:/&&f{print "VERSION-R:", f, $3}' || true

            # ABI symbols – now less sensitive
            if [[ "$elf" == *.so* ]] || readelf -h "$elf" 2>/dev/null | grep -q "DYN"; then
                nm -D --with-symbol-versions --defined-only --extern-only "$elf" 2>/dev/null | \
                awk -v p="$rel_path" '
                {
                    if ($1 ~ /^[0-9a-fA-F]+$/) { $1="" }
                    gsub(/^ +/, "")
                    if ($0 == "") next
                    # Get type and symbol name (second field after stripping address)
                    type = $1
                    name = $2
                    # Strip version suffix
                    gsub(/@.*$/, "", name)
                    # Use only basename of the library
                    lib = p
                    gsub(/^.*\//, "", lib)
                    print "SYMBOL:", lib, name
                }' || true
            fi
        done | sort -u

    rm -rf "$tmpdir"
}

info_a=$(extract_info "$pkg_a")
info_b=$(extract_info "$pkg_b")

# Compare NEEDED (now also less sensitive if you modified the output above)
needed_a=$(grep NEEDED <<< "$info_a" || true)
needed_b=$(grep NEEDED <<< "$info_b" || true)

need_diff=""
need_diff_out=""
if ! need_diff_out=$(diff <(echo "$needed_a") <(echo "$needed_b") 2>&1); then
    need_diff="NEEDED-LIBS:DIFFER"
fi

# Compare ABI symbols
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