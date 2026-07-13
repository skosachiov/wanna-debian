#!/usr/bin/env bash
set -euo pipefail

debug=0
compare_versions=0
tmpfiles=()

cleanup() {
    for item in "${tmpfiles[@]}"; do
        if [[ -d "$item" ]]; then
            rm -rf "$item"
        elif [[ -f "$item" ]]; then
            rm -f "$item"
        fi
    done
}
trap cleanup EXIT INT TERM HUP

usage() { 
    echo "Usage: $(basename "$0") [--debug] <pkg_a.deb|url> <pkg_b.deb|url>"
    echo "  --debug    Show detailed diff output"
    exit 1
}

# Parse arguments
args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug)
            debug=1
            shift
            ;;
        --help|-h)
            usage
            ;;
        -*)
            echo "ERROR: Unknown option: $1"
            usage
            ;;
        *)
            args+=("$1")
            shift
            ;;
    esac
done

# Restore positional arguments
set -- "${args[@]}"
[[ $# -eq 2 ]] || usage

resolve_pkg() {
    local arg="$1"
    if [[ "$arg" == http://* || "$arg" == https://* ]]; then
        local name=$(basename "$arg")
        local path="/tmp/${name}"
        (( debug )) && echo "Downloading $arg to $path" >&2
        if command -v wget &>/dev/null; then
            wget -qO "$path" "$arg"
        else
            curl -sLo "$path" "$arg"
        fi
        echo "$path"
    else
        realpath "$arg"
    fi
}

pkg_a=$(resolve_pkg "$1")
if [[ "$pkg_a" == /tmp/* ]]; then
    tmpfiles+=("$pkg_a")
fi

pkg_b=$(resolve_pkg "$2")
if [[ "$pkg_b" == /tmp/* ]]; then
    tmpfiles+=("$pkg_b")
fi

[[ -f "$pkg_a" ]] || { echo "ERROR: not a file: $pkg_a"; exit 1; }
[[ -f "$pkg_b" ]] || { echo "ERROR: not a file: $pkg_b"; exit 1; }

n_a=$(basename "$pkg_a")
n_b=$(basename "$pkg_b")

extract_info() {
    local deb="$1" tmpdir
    tmpdir=$(mktemp -d)
    tmpfiles+=("$tmpdir")

    dpkg-deb -x "$deb" "$tmpdir" >/dev/null 2>&1
    
    find "$tmpdir" -type f -exec file {} + 2>/dev/null \
        | awk -F: '/ELF/ {print $1}' \
        | while read -r elf; do
            local rel_path="${elf#$tmpdir/}"
            
            # NEEDED and SONAME
            readelf -d "$elf" 2>/dev/null | awk -v p="$rel_path" '/SONAME/ {gsub(/^\[|\]$/,"",$NF); print p, "SONAME:", $NF}'
            readelf -d "$elf" 2>/dev/null | awk -v p="$rel_path" '/NEEDED/ {gsub(/^\[|\]$/,"",$NF); print p, "NEEDED:", $NF}'
            readelf -V "$elf" 2>/dev/null | awk -v p="$rel_path" '/File:/{f=$5} /  Name:/&&f{print p, "VERSION-R:", f, $3}' || true
            
            if [[ "$elf" == *.so* ]] || readelf -h "$elf" 2>/dev/null | grep -q "DYN"; then
                nm -D --with-symbol-versions --defined-only --extern-only "$elf" 2>/dev/null | \
                awk -v p="$rel_path" '
                {
                    if ($1 ~ /^[0-9a-fA-F]+$/) { $1=""; gsub(/^ +/, "") }
                    if ($0 == "" || NF < 2) next
                    type = ($1 == "I" || $1 == "i") ? "T" : $1
                    name = $2
                    gsub(/@.*$/, "", name)
                    if (name ~ /^_Z/) next
                    lib = p; gsub(/^.*\//, "", lib)
                    print "SYMBOL:", lib, name, type
                }' || true
            fi
        done | sort -u
}

info_a_file=$(mktemp)
tmpfiles+=("$info_a_file")
extract_info "$pkg_a" > "$info_a_file"
info_a=$(< "$info_a_file")

info_b_file=$(mktemp)
tmpfiles+=("$info_b_file")
extract_info "$pkg_b" > "$info_b_file"
info_b=$(< "$info_b_file")

# Compare NEEDED libraries
needed_a=$(grep NEEDED <<< "$info_a" || true)
needed_b=$(grep NEEDED <<< "$info_b" || true)

need_diff=""
need_diff_out=""
if ! need_diff_out=$(diff <(echo "$needed_a") <(echo "$needed_b") 2>&1); then
    need_diff="NEEDED-LIBS:DIFFER"
fi

# Compare version
version_diff=""
version_diff_out=""
version_a=$(grep VERSION-R <<< "$info_a" || true)
version_b=$(grep VERSION-R <<< "$info_b" || true)
if ! version_diff_out=$(diff <(echo "$version_a") <(echo "$version_b") 2>&1); then
    version_diff="VERSIONS:DIFFER"
fi

# Compare ABI symbols (exclude VERSION-R and NEEDED)
syms_a=$(grep -v "NEEDED\|VERSION-R" <<< "$info_a" | grep . || true)
syms_b=$(grep -v "NEEDED\|VERSION-R" <<< "$info_b" | grep . || true)
abi_diff=""
abi_diff_out=""
if ! abi_diff_out=$(diff <(echo "$syms_a") <(echo "$syms_b") 2>&1); then
    abi_diff="ABI:DIFFER"
fi

# Build results
diffs=()
[[ -n "$abi_diff" ]] && diffs+=("$abi_diff")
[[ -n "$need_diff" ]] && diffs+=("$need_diff")
[[ -n "$version_diff" ]] && diffs+=("$version_diff")

if [[ ${#diffs[@]} -eq 0 ]]; then
    echo "$n_a $n_b OK"
else
    joined=$(IFS=' '; echo "${diffs[*]}")
    echo "$n_a $n_b $joined"
    if (( debug )); then
        [[ -n "$need_diff" ]] && echo "--- NEEDED-LIBS diff ---"$'\n'"$need_diff_out"
        [[ -n "$version_diff" ]] && echo "--- VERSION-REQ diff ---"$'\n'"$version_diff_out"
        [[ -n "$abi_diff" ]] && echo "--- ABI-SYMBOLS diff ---"$'\n'"$abi_diff_out"
    fi
fi