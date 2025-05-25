#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: cat [pkgs_list] | $0 [basename] [newer_suffix] [older_suffix]"
    echo "Example: echo gnome-core | $0 gnome trixie bullseye"
    echo "Example: cat gnome.txt | $0 gnome trixie bullseye"
    exit 0
fi

cat > $1.bin.00

./backport-bin.sh $1.bin $2 $3

cat $1.bin.[0-9]* | sort -u > $1.src.00

./backport-src.sh $1.src $2 $3

cat $1.src.[0-9]* | sort -u | python3 pre-dose.py -a $2_Packages $2_Sources | cut -f 1 -d " " | sort -u > $1.src.all
