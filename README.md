# wanna-debian

## pre-dose workflow

### get metadata

```
wget -O bullseye_Packages.gz http://ftp.debian.org/debian/dists/bullseye/main/binary-amd64/Packages.gz && gunzip bullseye_Packages.gz
wget -O trixie_Packages.gz http://ftp.debian.org/debian/dists/trixie/main/binary-amd64/Packages.gz && gunzip trixie_Packages.gz

wget -O bullseye_Sources.gz http://ftp.debian.org/debian/dists/bullseye/main/source/Sources.gz && gunzip bullseye_Sources.gz
wget -O trixie_Sources.gz http://ftp.debian.org/debian/dists/trixie/main/source/Sources.gz && gunzip trixie_Sources.gz
```

### select packages

#### gnome backport example

* https://people.debian.org/~fpeters/gnome/debian-gnome-48-status.html
* https://wiki.debian.org/PkgQtKde/TrixieReleasePlans

```
awk -v RS='\n\n' '/Version: 4[3-8]\..*GNOME Main/' trixie_Sources | grep ^Package: | cut -f 2 -d ' ' | sort -u > gnome.00
```

#### kde backport example

```
awk -v RS='\n\n' '/Version: 6\.3\.4.*KDE Main/' trixie_Sources | grep ^Package: > kde.00
awk -v RS='\n\n' '/Version: 24\.12.*KDE Main/' trixie_Sources | grep ^Package: >> kde.00
awk -v RS='\n\n' '/Version: 25\.0.*KDE Main/' trixie_Sources | grep ^Package: >> kde.00
sort -u -o kde.00 kde.00
```

### workflow

```
cat backport.00 | python3 pre-dose.py trixie_Sources bullseye_Sources > modified_Sources

dose-builddebcheck --deb-native-arch=amd64 -e -f bullseye_Packages modified_Sources | \
    grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > backport.01
```

#### sanitize repo

`bash backport.sh nu trixie bullseye 2> nu.err`

#### iter backport

`bash backport.sh backport trixie bullseye 2> backport.err`

#### diff backport and nu

`comm -23 gnome.list nu.list`
