# wanna-debian

## pre-dose workflow

### intro

Pre-doce is a specialized workflow designed to analyze and backport Debian packages from newer releases, such as trixie, to older stable releases like bullseye. By automating dependency resolution and compatibility assessment, it efficiently identifies which packages can be cleanly backported and which cannot due to unsatisfied dependencies.

The workflow begins with binary dependency resolution, analyzing which packages can be migrated without conflicts. This initial assessment is then processed by dose-debcheck, which systematically verifies package installability against the target release’s repository. The output is fed into dose-builddebcheck, the core iterative engine that refines dependency resolution by cycling through source package metadata.

During each iteration, unsatisfied dependencies are stripped from the metadata, and the verification process repeats with the updated constraints. Since the package databases may already contain unresolvable dependencies such as missing or incompatible libraries these are preemptively filtered out before processing. This step minimizes redundant checks and accelerates convergence toward a viable solution.

By combining dose-debcheck and dose-builddebcheck, Pre-doce ensures an efficient and reliable backporting process. It reduces manual effort, precisely pinpoints problematic dependencies, and automates the end-to-end workflow, making it an indispensable tool for Debian maintainers and developers.

### apt

`apt update && apt install dose-* wget vim git bash-com* man`

### get metadata

```
wget -O bullseye_Packages.gz http://ftp.debian.org/debian/dists/bullseye/main/binary-amd64/Packages.gz && gunzip bullseye_Packages.gz
wget -O trixie_Packages.gz http://ftp.debian.org/debian/dists/trixie/main/binary-amd64/Packages.gz && gunzip trixie_Packages.gz

wget -O bullseye_Sources.gz http://ftp.debian.org/debian/dists/bullseye/main/source/Sources.gz && gunzip bullseye_Sources.gz
wget -O trixie_Sources.gz http://ftp.debian.org/debian/dists/trixie/main/source/Sources.gz && gunzip trixie_Sources.gz
```

### find unmet dependencies before metadata implantation

```
echo "" > nu.bin.00
./backport-bin.sh nu.bin trixie bullseye
mv nu.bin.all bullseye_Packages.broken.before
```
```
echo "" > nu.src.00
./backport-src.sh nu.src trixie bullseye
mv nu.src.all bullseye_Sources.broken.before
```

### select binary packages

Get list of sections in "trixie":

https://packages.debian.org/source/trixie/

or

https://people.debian.org/~fpeters/gnome/debian-gnome-48-status.html

`echo gnome-core | python pre-dose.py -e trixie_Packages trixie_Sources | sort -u > gnome.txt`

or

`awk -v RS='\n\n' '/Version: 4[3-8]\..*GNOME Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' | sort -u > gnome.txt`

or

https://wiki.debian.org/PkgQtKde/TrixieReleasePlans

```
awk -v RS='\n\n' '/Version:.*6\.3\.[4-5].*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' > kde.txt
awk -v RS='\n\n' '/Version:.*24\.12.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' >> kde.txt
awk -v RS='\n\n' '/Version:.*25\.0.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' >> kde.txt
sort -u -o kde.txt kde.txt
```

### run resolver

`cat gnome.txt | ./backport.sh gnome trixie bullseye`

or 

`cat kde.txt | ./backport.sh kde trixie bullseye`

### view result

`cat gnome.src.all`

`cat kde.src.all`

## man dose-ceve

Find all the reverse binary dependencies of the package patchutils:
```
dose-ceve --deb-native-arch amd64 -r patchutils -T deb \
        deb:///var/lib/apt/lists/*_dists_sid_main_binary-amd64_Packages \
        | grep-dctrl -n -s Package '' | sort -u
```
Find all the source packages that (directly or indirectly) build depend on patchutils:
```
dose-ceve -T debsrc --deb-native-arch=amd64 -r patchutils \
        debsrc:///var/lib/apt/lists/*_dists_sid_main_source_Sources \
        deb:///var/lib/apt/lists/*_dists_sid_main_binary-amd64_Packages \
        | grep-dctrl -n -s Package '' | sort -u
```

## sbuild test

```
podman run -v ~/sbuild:/root/.cache:z,exec,dev -it -e LANG=C.UTF8 debian:trixie /bin/bash -l
apt update && apt -y upgrade
apt install sbuild mmdebstrap uidmap
sbuild --chroot-mode=plain ... package.dsc
```