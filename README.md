# wanna-debian

## pre-dose workflow

### intro

Pre-doce is a specialized workflow designed to analyze and backport Debian packages from newer releases, such as trixie, to older stable releases like bookworm. By automating dependency resolution and compatibility assessment, it efficiently identifies which packages can be cleanly backported and which cannot due to unsatisfied dependencies.

The workflow begins with binary dependency resolution, analyzing which packages can be migrated without conflicts. This initial assessment is then processed by dose-debcheck, which systematically verifies package installability against the target release’s repository. The output is fed into dose-builddebcheck, the core iterative engine that refines dependency resolution by cycling through source package metadata.

During each iteration, unsatisfied dependencies are stripped from the metadata, and the verification process repeats with the updated constraints. Since the package databases may already contain unresolvable dependencies such as missing or incompatible libraries these are preemptively filtered out before processing. This step minimizes redundant checks and accelerates convergence toward a viable solution.

By combining dose-debcheck and dose-builddebcheck, Pre-doce ensures an efficient and reliable backporting process. It reduces manual effort, precisely pinpoints problematic dependencies, and automates the end-to-end workflow, making it an indispensable tool for Debian maintainers and developers.

In the context of package backporting, Pre-doce employs topological sorting to determine the optimal build order for source packages, ensuring that dependencies are available at each step of the compilation process. Since Debian packages often depend on one another in complex ways, a correct build sequence is essential to avoid failures due to missing build-dependencies.

### apt

`apt update && apt install python3-apt dose-* wget vim git bash-com* man`

### get metadata

```
wget -O bookworm_Packages.gz http://ftp.debian.org/debian/dists/bookworm/main/binary-amd64/Packages.gz && gunzip bookworm_Packages.gz
wget -O trixie_Packages.gz http://ftp.debian.org/debian/dists/trixie/main/binary-amd64/Packages.gz && gunzip trixie_Packages.gz

wget -O bookworm_Sources.gz http://ftp.debian.org/debian/dists/bookworm/main/source/Sources.gz && gunzip bookworm_Sources.gz
wget -O trixie_Sources.gz http://ftp.debian.org/debian/dists/trixie/main/source/Sources.gz && gunzip trixie_Sources.gz
```

### find unmet dependencies before metadata implantation

```
echo "" > nu.bin.00
./backport-bin.sh nu.bin trixie bookworm
mv nu.bin.all bookworm_Packages.broken.before
```
```
echo "" > nu.src.00
./backport-src.sh nu.src trixie bookworm
mv nu.src.all bookworm_Sources.broken.before
```

### select binary packages

Get list of sections in "trixie":

https://packages.debian.org/source/trixie/

or

https://people.debian.org/~fpeters/gnome/debian-gnome-48-status.html

`echo gnome-core | python pre-dose.py -e trixie_Packages trixie_Sources | cut -f 1 -d ' ' | sort -u > gnome.txt`

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

`cat gnome.txt | ./backport.sh gnome trixie bookworm`

or 

`cat kde.txt | ./backport.sh kde trixie bookworm`

### view result

`cat gnome.src.all`

`cat kde.src.all`

### topological sort result

`cat gnome.src.all | python3 pre-dose.py --log-file gnome.src.log -t trixie_Sources bookworm_Sources > gnome.src.toposort`

## man dose-ceve

Find all the source packages that (directly or indirectly) build depend on patchutils (depth 2):
```
dose-ceve --deb-native-arch=amd64 -r patchutils -T debsrc --depth 2 debsrc://trixie_Sources deb://trixie_Packages \
        | grep-dctrl -n -s Package '' | sort -u
```

Find all the reverse binary dependencies of the package patchutils:
```
dose-ceve --deb-native-arch amd64 -r patchutils -T deb --depth 2 deb://trixie_Packages \
        | grep-dctrl -n -s Package '' | sort -u
```

Find all build deps for build-essential:
```
dose-ceve --deb-native-arch=amd64 -r build-essential -T deb --depth 1 \
    debsrc://trixie_Sources deb://trixie_Packages | grep-dctrl -n -s Package '' | sort -u 
```

## sources toposort with dot graph

`echo build-essential | python3 pre-dose.py --log-file build-essential.log -e 2 trixie_Sources bookworm_Sources > build-essential.src.txt`

`tac build-essential.src.txt | python3 pre-dose.py --log-file build-essential.log -t --dot build-essential.dot trixie_Sources bookworm_Sources > build-essential.toposort.txt`

`xdot build-essential.dot`

## sbuild test

```
podman run -v ~/sbuild:/root/.cache:z,exec,dev -it -e LANG=C.UTF8 debian:12 /bin/bash -l
apt update && apt -y upgrade
apt install sbuild mmdebstrap uidmap devscripts
apt install vim
mmdebstrap --include=ca-certificates --variant=buildd bookworm ~/.cache/sbuild
chmod a+w /root/.cache/sbuild/dev/null 
sbuild -d bookworm package.dsc
```

```
Types: deb-src
URIs: http://deb.debian.org/debian
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
```

```
cat /etc/schroot/chroot.d/bookworm.conf 
[bookworm]
directory=/root/.cache/sbuild
users=root
groups=root,sbuild
root-groups=root
aliases=unstable,default
```

`cat build.txt | xargs -I {} apt source --download-only {}`
