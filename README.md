# wanna-debian

## pre-dose workflow

Pre-doce is a workflow for analyzing and backporting Debian packages from newer releases (e.g., trixie) to older stable releases (e.g., bullseye). It automates dependency resolution and identifies packages that can be cleanly backported, as well as those with unsatisfied dependencies.

### get metadata

```
wget -O bullseye_Packages.gz http://ftp.debian.org/debian/dists/bullseye/main/binary-amd64/Packages.gz && gunzip bullseye_Packages.gz
wget -O trixie_Packages.gz http://ftp.debian.org/debian/dists/trixie/main/binary-amd64/Packages.gz && gunzip trixie_Packages.gz

wget -O bullseye_Sources.gz http://ftp.debian.org/debian/dists/bullseye/main/source/Sources.gz && gunzip bullseye_Sources.gz
wget -O trixie_Sources.gz http://ftp.debian.org/debian/dists/trixie/main/source/Sources.gz && gunzip trixie_Sources.gz
```

### select binary packages

#### gnome backport example

* https://people.debian.org/~fpeters/gnome/debian-gnome-48-status.html
* https://wiki.debian.org/PkgQtKde/TrixieReleasePlans

`echo gnome-core | python pre-dose.py -e trixie_Packages trixie_Sources | sort`

or

```
awk -v RS='\n\n' '/Version: 4[3-8]\..*GNOME Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' | sort -u > gnome.bin.00
```

#### kde backport example

```
awk -v RS='\n\n' '/Version:.*6\.3\.4.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' > kde.bin.00
awk -v RS='\n\n' '/Version:.*24\.12.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' >> kde.bin.00
awk -v RS='\n\n' '/Version:.*25\.0.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' >> kde.bin.00
sort -u -o kde.00 kde.00
```

### main loop binary packages

`bash backport-bin.sh gnome.bin trixie bullseye 2> gnome.bin.log`

#### preparing the start file

`cat gnome.bin.* | sort -u > gnome.src.00`

### main loop sources

```
cat backport.00 | python3 pre-dose.py -p trixie_Packages trixie_Sources bullseye_Sources > modified_Sources

dose-builddebcheck --deb-native-arch=amd64 -e -f bullseye_Packages modified_Sources | \
    grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > backport.01
```

#### main loop automation

`bash backport.sh gnome.src trixie bullseye 2> gnome.src.log`

#### sanitize repo

`bash backport.sh nu.src trixie bullseye 2> nu.src.log`

#### grep result

* with binary `cat gnome.src.[0-9]* | sort -u`
* source only `grep -v error: gnome.src.log | awk -F': ' '{print $2}' | sort -u`

#### diff backport and nu

`comm -23 gnome.src.list nu.src.list`

with versions `comm -23 gnome.src.list nu.src.list | python3 pre-dose.py -a trixie_Sources bullseye_Sources | grep '='`
