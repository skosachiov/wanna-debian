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

cat $filename | python3 pre-dose.py $2_Packages $3_Packages > modified_Packages

dose-debcheck --deb-native-arch=amd64 -e -f $3_Packages \
    | grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > $base_name.broken.before

while [ -s "$filename" ]; do
    echo "Processing $filename"
    ((counter++))
    next_filename=$(printf "%s.%02d" "$base_name" $counter)
    
    dose-debcheck --deb-native-arch=amd64 -e -f modified_Packages \
        | grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > $next_filename
    cp -f modified_Packages modified_Packages.prev

    if cmp -s "$filename" "$next_filename"; then
        echo "Stopping: '$next_filename' has identical content to '$filename'"
        break
    fi

    comm -13 $filename $next_filename \
        | python3 pre-dose.py $2_Packages modified_Packages > modified_Packages.tmp
    mv -f modified_Packages.tmp modified_Packages

    cat $base_name.broken.before $base_name.[0-9]* \
        | sort -u | python3 pre-dose.py -d $2_Packages modified_Packages > modified_Packages.tmp
    mv -f modified_Packages.tmp modified_Packages
           
    filename="$next_filename"
done

echo "Stopping: '$filename' is empty"