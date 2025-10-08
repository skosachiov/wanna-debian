#!/bin/bash

SD="$(dirname "${BASH_SOURCE[0]}")"

# print help
if [ -z "$1" ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: cat <pkgslist> | backport [--checkonly] [--binonly] [--removeonly] <basename> <newerprefix> <olderprefix>"
    echo ""
    echo "The script backport expects to find the following metadata files in the current directory:"
    echo "newerprefix_Packages, newerprefix_Sources, olderprefix_Packages, olderprefix_Sources"
    echo ""
    echo "Example: echo gnome-core | backport gnome-core sid trixie"
    echo "Example: cat debootstrap.list | backport minimal sid empty"
    exit 0
fi

OPT_CHECKONLY=false
OPT_BINONLY=false
OPT_REMOVEONLY=false
EXTRA_PARAMS=()
# Process options
while [[ $# -gt 0 ]]; do
    case "$1" in
        --checkonly)
            OPT_CHECKONLY=true
            shift
            ;;
        --binonly)
            OPT_BINONLY=true
            shift
            ;;
        --removeonly)
            OPT_REMOVEONLY=true
            shift
            ;;            
        *)
            # Break out of the loop when we hit the first non-option argument
            break
            ;;
    esac
done

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

cat $filename.bin | python3 $SD/predose.py --log-file $base_name.log $2_Packages $3_Packages > ${base_name}_Packages
cat $filename.bin | python3 $SD/predose.py --log-file $base_name.log -s $2_Sources $3_Sources | sort -u > $filename.src
cat $filename.src | python3 $SD/predose.py --log-file $base_name.log $2_Sources $3_Sources > ${base_name}_Sources
echo "" > $filename.src

while [[ -s "$filename.bin" || -s "$filename.src"  ]]; do

    echo "Processing $filename"
    ((counter++))
    next_filename=$(printf "%s.%03d" "$base_name" $counter)

    # keep resolve up
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-up $2_Packages ${base_name}_Packages > $filename.bin.tmp && \
        cat $filename.bin.tmp >> $filename.bin && rm -f $filename.bin.tmp
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-up $2_Sources ${base_name}_Sources > $filename.bin.tmp && \
        cat $filename.bin.tmp >> $filename.bin && rm -f $filename.bin.tmp

    # remove bin target packages and groups
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --remove ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-group $3_Packages ${base_name}_Packages \
        | python3 $SD/predose.py --log-file $base_name.log --remove ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-up $2_Packages ${base_name}_Packages \
        | python3 $SD/predose.py --log-file $base_name.log --remove ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages        

    if [ "$OPT_BINONLY" = false ]; then
    # remove src target sources
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-src --provide $3_Packages $3_Sources ${base_name}_Sources \
        | python3 $SD/predose.py --log-file $base_name.log --remove ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-up $2_Sources ${base_name}_Sources \
        | python3 $SD/predose.py --log-file $base_name.log --remove ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources
    fi

    # convert bin to src
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-src --provide $2_Packages $2_Sources ${base_name}_Sources \
        | sort -u > $next_filename.src

    if [ "$OPT_REMOVEONLY" = false ]; then # skip all implantations if true

    # bin-bin implantation
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log $2_Packages ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages                
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-group $2_Packages ${base_name}_Packages \
        | python3 $SD/predose.py --log-file $base_name.log $2_Packages ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-up $2_Packages ${base_name}_Packages \
        | python3 $SD/predose.py --log-file $base_name.log $2_Packages ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages                

    # src-src implantation
    cat $next_filename.src \
        | python3 $SD/predose.py --log-file $base_name.log --provide $2_Packages $2_Sources ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources

    # src-src dependent implantation if dep not found
    cat $filename.bin \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-up $2_Sources ${base_name}_Sources \
        | python3 $SD/predose.py --log-file $base_name.log --provide $2_Packages $2_Sources ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources

    # src-bin implantation
    cat $next_filename.src \
        | python3 $SD/predose.py --log-file $base_name.log --resolve-bin $2_Sources ${base_name}_Sources \
        | python3 $SD/predose.py --log-file $base_name.log $2_Packages ${base_name}_Packages > ${base_name}_Packages.tmp && \
        mv -f ${base_name}_Packages.tmp ${base_name}_Packages

    fi # removeonly

    echo -n > $next_filename.bin

    # check binary packages in dependencies, broken due to low dependent versions
    dose-debcheck --latest 1 --deb-native-arch=amd64 -e -f ${base_name}_Packages | tee \
        >(grep -oE 'unsat-.*: [^|]*(|.*)?' | tr '|' '\n' | grep -oP 'unsat-dependency: \K[^:| ]+' | sort -u >> $next_filename.bin) \
        >(grep -B 4 -P "^\s{6}unsat-.*\((<|=)" | grep -oP '(package:|version:) \K\S+' | paste -d "=" - - | sort -u >> $next_filename.bin) \
        >> ${base_name}.debcheck.log &
    
    pid=$!

    # check src and append to bin, broken due to low dependent versions
    if [ "$OPT_CHECKONLY" = true ]; then
        EXTRA_PARAMS=(--checkonly "$(paste -sd, <(cat $base_name.*.src | grep -v "^\s*$"))")
    fi
    if [ "$OPT_BINONLY" = false ]; then
    dose-builddebcheck "${EXTRA_PARAMS[@]}" --latest 1 --deb-native-arch=amd64 -e -f ${base_name}_Packages ${base_name}_Sources | tee \
        >(grep -oE 'unsat-.*: [^|]*(|.*)?' | tr '|' '\n' | grep -oP 'unsat-dependency: \K[^:| ]+' | sort -u >> $next_filename.bin) \
        >(grep -B 4 -P "^\s{6}unsat-.*\((<|=)" | grep -oP '(package:|version:) \K\S+' | paste -d "=" - - | sort -u >> $next_filename.bin) \
        >> ${base_name}.builddebcheck.log
    fi

    wait $pid

    sort -u -o "$next_filename.bin" "$next_filename.bin"
    sort -u -o "$next_filename.src" "$next_filename.src"

    cp -f ${base_name}_Sources ${base_name}_Sources.prev
    cp -f ${base_name}_Packages ${base_name}_Packages.prev

    if cmp -s "$filename.bin" "$next_filename.bin" && cmp -s "$filename.src" "$next_filename.src"; then
        echo "Stopping: '$next_filename' has identical content to '$filename'"
        exit 0
    fi

    if [ $counter -ge 999 ]; then
        echo "Iteration limit reached"
        exit 1
    fi

    filename="$next_filename"
done

echo "Stopping: '$filename.bin' and '$filename.src' is empty"
