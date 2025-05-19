#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 <base_filename>"
    echo "Example: $0 example"
    exit 1
fi

base_name="$1"
counter=0

filename=$(printf "%s.%02d" "$base_name" $counter)

if [ ! -s "$filename" ]; then
    echo "Error: Initial file '$filename' is empty or doesn't exist"
    exit 1
fi

cat $filename | python3 pre-dose.py $2_Sources $3_Sources > modified_Sources

while [ -s "$filename" ]; do
    echo "Processing $filename"
    ((counter++))
    next_filename=$(printf "%s.%02d" "$base_name" $counter)
    
    dose-builddebcheck --deb-native-arch=amd64 -e -f $3_Packages modified_Sources | grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > $next_filename

    comm -23 $next_filename $filename | python3 pre-dose.py -d $2_Sources modified_Sources > modified_Sources.tmp
    mv -f modified_Sources.tmp modified_Sources
    
    comm -23 $next_filename $filename | python3 pre-dose.py $2_Sources modified_Sources > modified_Sources.tmp
    mv -f modified_Sources.tmp modified_Sources
    
    filename="$next_filename"
done

echo "Stopping: '$filename' is empty"