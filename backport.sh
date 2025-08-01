#!/bin/bash

SD="$(dirname "${BASH_SOURCE[0]}")"

# print help
if [ -z "$1" ]; then
    echo "Usage: cat <pkgslist> | $0 <basename> <newerprefix> <olderprefix>"
    echo ""
    echo "The script $0 expects to find the following metadata files in the current directory:"
    echo "newerprefix_Packages, newerprefix_Sources, olderprefix_Packages, olderprefix_Sources"
    echo ""
    echo "Example: echo gnome-core | $0 gnome-core sid trixie"
    echo "Example: cat debootstrap.list | $0 minimal sid empty"
    exit 0
fi

# warning if not installed
if ! dpkg -l | grep -q 'dose-distcheck'; then
    echo "Warning: dose-distcheck package is not installed. Exiting."
    exit 1
fi

if ! dpkg -l | grep -q 'dose-builddebcheck'; then
    echo "Warning: dose-builddebcheck package is not installed. Exiting."
    exit 1
fi

base_name="$1"
counter=0

filename=$(printf "%s.%03d" "$base_name" $counter)

cat > $filename.bin

cat $filename.bin | python3 $SD/pre-dose.py --log-file $base_name.log $2_Packages $3_Packages > ${base_name}_Packages
cat $filename.bin | python3 $SD/pre-dose.py --log-file $base_name.log -s $2_Sources $3_Sources | sort -u > $filename.src
cat $filename.src | python3 $SD/pre-dose.py --log-file $base_name.log $2_Sources $3_Sources > ${base_name}_Sources
echo " " > $filename.src

while [[ -s "$filename.bin" || -s "$filename.src"  ]]; do

    echo "Processing $filename"
    ((counter++))
    next_filename=$(printf "%s.%03d" "$base_name" $counter)

    # remove bin target groups
    cat $filename.bin \
        | python3 $SD/pre-dose.py --log-file $base_name.log --resolve-group $2_Packages ${base_name}_Packages \
        | python3 $SD/pre-dose.py --log-file $base_name.log -r $2_Packages ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages

    # convert bin to src
    cat $filename.bin \
        | python3 $SD/pre-dose.py --log-file $base_name.log --resolve-src --provide $2_Packages $2_Sources ${base_name}_Sources \
        | sort -u > $next_filename.src    

    # src-src implantation
    cat $next_filename.src \
        | python3 $SD/pre-dose.py --log-file $base_name.log --provide $2_Packages $2_Sources ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources

    # src-bin implantation
    cat $next_filename.src \
        | python3 $SD/pre-dose.py --log-file $base_name.log --resolve-bin $2_Sources ${base_name}_Sources \
        | python3 $SD/pre-dose.py --log-file $base_name.log $2_Packages ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages

    # check binary packages in dependencies
    dose-debcheck --latest 1 --deb-native-arch=amd64 -e -f ${base_name}_Packages \
        | grep -oE 'unsat-.*: [^|]*(|.*)?' | tr '|' '\n' | grep -oE '\b[a-zA-Z][a-zA-Z0-9_.+-]+:[a-zA-Z0-9_]+\b' | cut -d: -f1 | sort -u > $next_filename.bin

    # check binary packages that broken due to low dependent versions
    dose-debcheck --latest 1 --deb-native-arch=amd64 -e -f ${base_name}_Packages \
        | grep -B 3 -P "^\s{6}unsat-.*\((<|=)" | grep -e package: | awk '{print $2}' | sort -u >> $next_filename.bin

    # check src and append to bin
    dose-builddebcheck --latest 1 --deb-native-arch=amd64 -e -f ${base_name}_Packages ${base_name}_Sources \
        | grep "unsat-" | awk '{print $2}' | cut -f 1 -d ":" | sort -u >> $next_filename.bin

    sort -u -o "$next_filename.bin" "$next_filename.bin"
    sort -u -o "$next_filename.src" "$next_filename.src"

    cp -f ${base_name}_Sources ${base_name}_Sources.prev
    cp -f ${base_name}_Packages ${base_name}_Packages.prev

    if cmp -s "$filename.bin" "$next_filename.bin" && cmp -s "$filename.src" "$next_filename.src"; then
        echo "Stopping: '$next_filename' has identical content to '$filename'"
        exit 0
    fi

    filename="$next_filename"
done

echo "Stopping: '$filename.bin' and '$filename.src' is empty"
