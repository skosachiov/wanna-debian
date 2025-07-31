# wanna-debian

## pre-dose

Pre-dose is a small set of Python and Bash scripts designed for analyzing and backporting Debian packages from
newer releases (e.g., Sid) to older stable versions (e.g., Trixie or Bookworm).

Pre-dose iteratively attempts to solve some limitations of Debian's standard metadata analyzers - dose-distcheck and dose-builddebcheck, specifically:
* Termination of dose scanning after the first unresolved dependency
* Lack of topological sorting in dependency output
* No built-in mechanism for easy metadata backporting

Given the following inputs:
* A list of packages to backport
* Metadata from the newer repository
* Metadata from the target old repository (can be empty)

pre-dose automatically generates the following artifacts without manual intervention:
* An expanded list of source packages (with resolved dependencies) for backporting
* An expanded list of binary packages for backporting
* Updated and consistent build metadata for the target repository
* Updated and consistent binary package metadata for the target repository

Determining the full list may require up to 100 iterations, with each dose check taking up to 2 minutes.

### important notes

The build metadata of the target repository may have unresolved dependencies before backport emulation via metadata substitution. To identify these, it is necessary to first compute broken dependencies without any backport list (using an empty backport set). This allows comparing two sets:
* Packages to backport
* Packages needed to repair the target repository

If the user provides a list of source packages (e.g., from a Debian software section like packages.debian.org/trixie/), they must first be converted to binary packages before processing.

### workflow of backport.sh

The backport.sh script assumes that the input consists of binary package names.

The provided binary packages must replace their counterparts in the target repository. This means that the existing versions of these packages must first be removed.
Their "siblings" (all binary packages built from the same source in the target repository) must also be removed.

Next, the new packages (both source and binary) are extracted from the source repository and implanted into the respective metadata of the target repository.

The process then enters a verification phase using dose-debcheck and dose-builddebcheck, which assess whether the packages can be installed and built in the target repository. A new list of binary packages is accumulated to satisfy dependencies.

If the list is non-empty, the cycle repeats. If an iteration returns an empty list, the process stops.

### conclusion

By combining dose-debcheck and dose-builddebcheck, Pre-dose provides an efficient and reliable backporting process. It reduces manual effort, accurately identifies problematic dependencies, and automates the entire workflow, making it an indispensable tool for Debian developers and maintainers.

## pre-dose examples

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

```
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
```

### debootstrap repo calculation

`cat /tmp/bootstrap.list | ./backport.sh bootstrap trixie empty &`
