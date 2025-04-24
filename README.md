# wanna-debian

## pre-dose

```
wget -O bullseye_Packages.gz http://ftp.debian.org/debian/dists/bullseye/main/binary-amd64/Packages.gz && gunzip bullseye_Packages.gz
wget -O trixie_Packages.gz http://ftp.debian.org/debian/dists/trixie/main/binary-amd64/Packages.gz && gunzip trixie_Packages.gz

wget -O bullseye_Sources.gz http://ftp.debian.org/debian/dists/bullseye/main/source/Sources.gz && gunzip bullseye_Sources.gz
wget -O trixie_Sources.gz http://ftp.debian.org/debian/dists/trixie/main/source/Sources.gz && gunzip trixie_Sources.gz
```

* https://people.debian.org/~fpeters/gnome/debian-gnome-48-status.html
* https://wiki.debian.org/PkgQtKde/TrixieReleasePlans

```
awk -v RS='\n\n' '/Version: 4[3-8]\..*GNOME Main/' trixie_Sources | grep ^Package: | cut -f 2 -d ' ' > gnome.00

vim gnome.00

cat gnome.00 | python pre-dose.py trixie_Sources bullseye_Sources > bullseye_Sources.gnome.00

dose-builddebcheck --deb-native-arch=amd64 -e -f bullseye_Packages bullseye_Sources.gnome.00 | \
    grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > gnome.01

cat gnome.00 gnome.01 | python pre-dose.py trixie_Sources bullseye_Sources > bullseye_Sources.gnome.01

dose-builddebcheck --deb-native-arch=amd64 -e -f bullseye_Packages bullseye_Sources.gnome.01 | \
    grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > gnome.02

cat gnome.00 gnome.01 gnome.02 | python pre-dose.py trixie_Sources bullseye_Sources > bullseye_Sources.gnome.02

...
```

```
awk -v RS='\n\n' '/Version: 6\.3\.4.*KDE Main/' trixie_Sources | grep ^Package:
awk -v RS='\n\n' '/Version: 24\.12.*KDE Main/' trixie_Sources | grep ^Package:
awk -v RS='\n\n' '/Version: 25\.0.*KDE Main/' trixie_Sources | grep ^Package:
```