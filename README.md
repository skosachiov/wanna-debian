# wanna-debian

## pre-dose workflow

### intro

Pre-doce is a specialized workflow designed to analyze and backport Debian packages from newer releases, such as sid, to older stable releases like trixie or bookworm. By automating dependency resolution and compatibility assessment, it efficiently identifies which packages can be cleanly backported and which cannot due to unsatisfied dependencies.

The workflow begins with binary dependency resolution, analyzing which packages can be migrated without conflicts. This initial assessment is then processed by dose-debcheck, which systematically verifies package installability against the target release’s repository. The output is fed into dose-builddebcheck, the core iterative engine that refines dependency resolution by cycling through source package metadata.

During each iteration, unsatisfied dependencies are implanted into the metadata, and the verification process repeats. Since the package databases may already contain unresolvable dependencies such as missing or incompatible libraries these are preemptively filtered out before processing. This step minimizes redundant checks and accelerates convergence toward a viable solution.

By combining dose-debcheck and dose-builddebcheck, Pre-doce ensures an efficient and reliable backporting process. It reduces manual effort, precisely pinpoints problematic dependencies, and automates the end-to-end workflow, making it an indispensable tool for Debian maintainers and developers.

In the context of package backporting, Pre-doce employs topological sorting to determine the optimal build order for source packages, ensuring that dependencies are available at each step of the compilation process. Since Debian packages often depend on one another in complex ways, a correct build sequence is essential to avoid failures due to missing build-dependencies.

### apt

`apt update && apt install python3-apt dose-* wget vim git bash-com* man`

### get metadata

```
wget -O bookworm_Packages.gz http://ftp.debian.org/debian/dists/bookworm/main/binary-amd64/Packages.gz && gunzip bookworm_Packages.gz
wget -O trixie_Packages.gz http://ftp.debian.org/debian/dists/trixie/main/binary-amd64/Packages.gz && gunzip trixie_Packages.gz
wget -O sid_Packages.gz http://ftp.debian.org/debian/dists/sid/main/binary-amd64/Packages.gz && gunzip sid_Packages.gz
wget -O unstable_Packages.gz http://ftp.debian.org/debian/dists/unstable/main/binary-amd64/Packages.gz && gunzip unstable_Packages.gz

wget -O bookworm_Sources.gz http://ftp.debian.org/debian/dists/bookworm/main/source/Sources.gz && gunzip bookworm_Sources.gz
wget -O trixie_Sources.gz http://ftp.debian.org/debian/dists/trixie/main/source/Sources.gz && gunzip trixie_Sources.gz
wget -O sid_Sources.gz http://ftp.debian.org/debian/dists/sid/main/source/Sources.gz && gunzip sid_Sources.gz
wget -O unstable_Sources.gz http://ftp.debian.org/debian/dists/unstable/main/source/Sources.gz && gunzip unstable_Sources.gz
```

### find unmet dependencies before metadata implantation

Broken in trixie:

```
echo "" | backport.sh broken-before trixie bookworm
```

### select binary packages

Get list of sections in "sid":

https://packages.debian.org/source/sid/

or

https://people.debian.org/~fpeters/gnome/debian-gnome-48-status.html

`echo gnome-core | python pre-dose.py -e 1 sid_Packages sid_Sources | cut -f 1 -d ' ' | sort -u > gnome.list`

or

`awk -v RS='\n\n' '/Version: 4[3-8]\..*GNOME Main/' sid_Packages | grep ^Package: | cut -f 2 -d ' ' | sort -u > gnome.list`

or

https://wiki.debian.org/PkgQtKde/TrixieReleasePlans

```
awk -v RS='\n\n' '/Version:.*6\.3\.[4-5].*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' > kde.list
awk -v RS='\n\n' '/Version:.*24\.12.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' >> kde.list
awk -v RS='\n\n' '/Version:.*25\.0.*KDE Main/' trixie_Packages | grep ^Package: | cut -f 2 -d ' ' >> kde.list
sort -u -o kde.list kde.list
```

### run resolver

`cat gnome.list | ./backport.sh gnome sid trixie`

or 

`cat kde.list | ./backport.sh kde sid trixie`

### view result

`cat gnome.*.src | sort -u`

`cat kde.*.src | sort -u`

### topological sort result

`cat gnome.*.src | sort -u | python3 pre-dose.py --log-file gnome.log -t sid_Sources trixie_Sources > gnome.toposort.src`

## man dose-ceve

Find all the source packages that (directly or indirectly) build depend on patchutils (depth 2):
```
dose-ceve --deb-native-arch=amd64 -r patchutils -T debsrc --depth 2 debsrc://sid_Sources deb://sid_Packages \
        | grep-dctrl -n -s Package '' | sort -u
```

Find all the reverse binary dependencies of the package patchutils:
```
dose-ceve --deb-native-arch amd64 -r patchutils -T deb --depth 2 deb://sid_Packages \
        | grep-dctrl -n -s Package '' | sort -u
```

Find all build deps for build-essential:
```
dose-ceve --deb-native-arch=amd64 -r build-essential -T deb --depth 1 \
    debsrc://sid_Sources deb://sid_Packages | grep-dctrl -n -s Package '' | sort -u 
```

## sources toposort with dot graph

`echo build-essential | python3 pre-dose.py --log-file build-essential.log -e 2 sid_Sources trixie_Sources > build-essential.list`

`tac build-essential.list | python3 pre-dose.py --log-file build-essential.log -t --dot build-essential.dot sid_Sources trixie_Sources > build-essential.toposort`

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
Suites: sid sid-updates
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

`cat build.list | xargs -I {} apt source --download-only {}`

## debootstrap repo example

debootstrap --print-debs trixie /tmp/trixie-chroot 2> /dev/null | tr " " "\n" > bootstrap.bin.list
cat bootstrap.bin.list | python3 pre-dose.py -s -p trixie_Packages trixie_Sources trixie_Sources 2> /dev/null | sort -u > bootstrap.src.list
echo "" > target_Sources
cat bootstrap.src.list | python3 pre-dose.py trixie_Sources target_Sources > target_Sources.tmp
mv target_Sources.tmp target_Sources
echo "" > target_Packages
cat bootstrap.src.list | python3 pre-dose.py -b trixie_Sources trixie_Sources \
        | python3 pre-dose.py trixie_Packages target_Packages > target_Packages.tmp
mv target_Packages.tmp target_Packages
dose-builddebcheck --latest 1 --deb-native-arch=amd64 -e -f target_Packages target_Sources

### debootstrap repo calculation

`cat /tmp/bootstrap.list  | ./backport.sh  bootstrap trixie empty &`
