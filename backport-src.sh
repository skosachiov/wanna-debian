#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 [basename.src] [newer_suffix] [older_suffix]"
    echo "Example: $0 gnome.src trixie bullseye"
    exit 1
fi

base_name="$1"
counter=0

filename=$(printf "%s.%02d" "$base_name" $counter)

if [ ! -s "$filename" ]; then
    echo "Error: Initial file '$filename' is empty or doesn't exist"
    exit 1
fi

cat $filename | python3 pre-dose.py --log-file $base_name.log $2_Sources $3_Sources > ${base_name}_Sources

if [ -e $3_Sources.broken.before ]; then
    cat $3_Sources.broken.before | sort -u \
        | python3 pre-dose.py --log-file $base_name.log -d $2_Sources ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources
fi

while [ -s "$filename" ]; do
    echo "Processing $filename"
    ((counter++))
    next_filename=$(printf "%s.%02d" "$base_name" $counter)
    
    dose-builddebcheck --deb-native-arch=amd64 -e -f $3_Packages ${base_name}_Sources \
        | grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > $next_filename
    cp -f ${base_name}_Sources ${base_name}_Sources.prev

    if cmp -s "$filename" "$next_filename"; then
        echo "Stopping: '$next_filename' has identical content to '$filename'"
        break
    fi
  
    comm -13 $filename $next_filename \
        | python3 pre-dose.py --log-file $base_name.log -p $3_Packages $2_Sources ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources

    cat $base_name.[0-9]* \
        | sort -u | python3 pre-dose.py --log-file $base_name.log -d -p $3_Packages $2_Sources ${base_name}_Sources > ${base_name}_Sources.tmp && \
        mv -f ${base_name}_Sources.tmp ${base_name}_Sources
    
    filename="$next_filename"
done

echo "Stopping: '$filename' is empty"