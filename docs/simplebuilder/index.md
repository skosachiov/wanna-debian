# simplebuilder

The Simple Debian package builder handles different source types based on URL patterns provided. The build task is received via stdin. Each line of the task is a link to a Debian package or its source code. After building or downloading each package, the artifacts are placed in a local repository and connected to the build environment, thus satisfying build dependencies for packages from subsequent lines. If a package version is already available in the connected repositories, a bin-nmu rebuild is automatically triggered. By default, the local `repository` and the log file `simplebuilder.log` will be located in `/tmp/workspace`. The build logs for a specific package are located in the repository and have the `.log` extension.

A successful build is indicated by the presence of `.deb` packages. The source package is copied to the local repository even if the build fails.

Please note that the local repository is enabled in the `/etc/apt/sources.list.d/simplebuilder.list` file and is disabled after `simplebuilder` completes its process. If you want to keep the local repository permanently enabled, please move the local repository entries, for example, to the `/etc/apt/sources.list` file. This may be necessary for the convenient use of consistency-checking tools, such as `dose-debcheck`.

## Build from a single .dsc file

`echo "https://example.com/package.dsc" | simplebuilder`

## Build from a Git repository

`echo "ssh://git@github.com/user/repo.git" | simplebuilder` \
or \
`echo "https://github.com/user/repo.git" | simplebuilder`

## Build from connected APT sources

If the string does *not contain a URI scheme*, the apt source operation will be called
To do this, you must connect the deb-src sources.

`echo vim | simplebuilder`

## Rebuid with suffix

`cat <file> | simplebuilder --suffix="+ubuntu1"`

## Bash-aware build from multiple sources
```
#!/bin/bash

simplebuilder --suffix="+ubuntu1" <<EOF
http://deb.debian.org/debian/pool/main/h/hello/hello_2.10-3.dsc
https://salsa.debian.org/debian/runit.git
EOF
apt-get purge -y --force-yes -f maven-debian-helper
apt-mark hold maven-debian-helper
simplebuilder --suffix="+ubuntu1" <<EOF
https://deb.debian.org/debian/pool/main/b/bcel/bcel_6.10.0-1.dsc
http://deb.debian.org/debian/pool/main/c/cowsay/cowsay_3.03+dfsg2-8.dsc
http://deb.debian.org/debian/pool/main/h/hello/hello_2.10-5.dsc
EOF
apt-mark unhold maven-debian-helper
simplebuilder --suffix="+ubuntu2" <<EOF
https://deb.debian.org/debian/pool/main/a/acct/acct_6.6.4-10.dsc
https://deb.debian.org/debian/pool/main/j/jq/jq_1.8.1-4.dsc
http://deb.debian.org/debian/pool/main/h/htop/htop_3.2.2-2.dsc
https://salsa.debian.org/debian/dash.git
http://ftp.debian.org/debian/pool/main/libs/libsepol/libsepol2_3.8.1-1_amd64.deb
http://deb.debian.org/debian/pool/main/libs/libselinux/libselinux_3.8.1-1.dsc
http://deb.debian.org/debian/pool/main/m/miller/miller_6.13.0-1.dsc
http://deb.debian.org/debian/pool/main/f/figlet/figlet_2.2.5-3.1.dsc
https://deb.debian.org/debian/pool/main/h/hello-traditional/hello-traditional_2.10-6.dsc
EOF
```

## Docker build
`docker build -f simplebuilder/Dockerfile --build-arg BASE_IMAGE=debian:12 -t my-builder:debian-12` \
or \
`docker build -f simplebuilder/Dockerfile --build-arg BASE_IMAGE=debian:13 -t my-builder:debian-13`

## Docker run
```
docker run -it --rm \
  -v $(pwd)/repository:/workspace/repository \
  debian-pkg-builder \
  bash -c "cat urls.txt | python3 simplebuilder.py"
```

## Big local repository

If your local repository has grown and the time it takes to scan binary packages has become long, or you've managed to stabilize the set of packages, you can rename the repository folder, for example, to `repository-stable`, connect it to the list of sources similar to the source file `/etc/apt/sources.list.d/simplebuilder.list`, and continue experimenting in the cleaned up `repository` folder.

## Never prefer the package from the specified repository

File `/etc/apt/preferences.d/99-block-php-repo`:

```
Package: php*
Pin: origin "your-repo-origin.com"
Pin-Priority: -1
```

## Checking repository

```
dose-debcheck --latest 1 --deb-native-arch=amd64 -e -f /var/lib/apt/lists/*_Packages \
        | grep -P "^\s{6}(unsat-|package:)" | paste - - | sort | uniq -c | sort -nr
```

## in a clean environment, podman and sbuild

```
podman run -it --privileged -v ~/git/podman:/root/git debian:13 /bin/bash
apt update && apt install -y debootstrap schroot sbuild libwww-perl
apt install -y man vim
ln -s /usr/share/debootstrap/scripts/trixie /usr/share/debootstrap/scripts/mytrixie
sbuild-createchroot --keyring=/usr/share/keyrings/mytrixie --include=eatmydata,ccache,gzip --extra-repository="deb http://security.debian.org/debian-security trixie-security main" mytrixie /srv/chroot/trixie-amd64-sbuild https://ftp.debian.org/debian
sed -i '/\/sys/s/^/#/' /etc/schroot/sbuild/fstab
sed -i '/\/sys/s/rw,bind/rw,rbind/' /etc/schroot/sbuild/fstab
umount -l ...
sbuild-createchroot --include=eatmydata,ccache,gzip forky /srv/chroot/forky-amd64-sbuild https://ftp.debian.org/debian
echo "Acquire::https { Verify-Peer "false"; Verify-Host "false"; }" > /srv/chroot/mytrixie-amd64-sbuild/etc/apt/apt.conf.d/99verify-https.conf
chmod a+rwx /srv/chroot/mytrixie-amd64-sbuild/dev/null
useradd -m user
sbuild-adduser user
su - user
sbuild -d mytrixie hello
sbuild -d mytrixie --lintian-opts="--suppress-tags changelog-distribution-does-not-match-changes-file,bad-distribution-in-changes-file,distribution-and-changes-mismatch" http://deb.debian.org/debian/pool/main/h/hello/hello_2.10-5.dsc
schroot -c chroot:trixie-amd64-sbuild
```
