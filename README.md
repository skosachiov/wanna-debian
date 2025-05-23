# wanna-debian

## pre-dose workflow

### intro

Pre-doce is a specialized workflow designed to analyze and backport Debian packages from newer releases, such as trixie, to older stable releases like bullseye. By automating dependency resolution and compatibility assessment, it efficiently identifies which packages can be cleanly backported and which cannot due to unsatisfied dependencies.

The workflow begins with binary dependency resolution, analyzing which packages can be migrated without conflicts. This initial assessment is then processed by dose-debcheck, which systematically verifies package installability against the target release’s repository. The output is fed into dose-builddebcheck, the core iterative engine that refines dependency resolution by cycling through source package metadata.

During each iteration, unsatisfied dependencies are stripped from the metadata, and the verification process repeats with the updated constraints. Since the package databases may already contain unresolvable dependencies such as missing or incompatible libraries these are preemptively filtered out before processing. This step minimizes redundant checks and accelerates convergence toward a viable solution.

By combining dose-debcheck and dose-builddebcheck, Pre-doce ensures an efficient and reliable backporting process. It reduces manual effort, precisely pinpoints problematic dependencies, and automates the end-to-end workflow, making it an indispensable tool for Debian maintainers and developers.

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

`cat gnome.bin.[0-9]* | sort -u > gnome.src.00`

### main loop sources

```
cat backport.00 | python3 pre-dose.py -p trixie_Packages trixie_Sources bullseye_Sources > modified_Sources

dose-builddebcheck --deb-native-arch=amd64 -e -f bullseye_Packages modified_Sources | \
    grep unsat-dep | awk '{print $2}' | cut -f 1 -d ":" | sort -u > backport.01
```

#### main loop automation

`bash backport-src.sh gnome.src trixie bullseye 2> gnome.src.log`

#### grep result

`cat gnome.src.[0-9]* | sort -u | python3 pre-dose.py -a trixie_Packages trixie_Sources | cut -f 1 -d " " | sort -u > gnome.src.all`
