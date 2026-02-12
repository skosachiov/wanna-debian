# simplebuilder

The Simple Debian package builder handles different source types based on URL patterns provided. The build task is received via stdin. Each line of the task is a link to a Debian package or its source code. After building or downloading each package, the artifacts are placed in a local repository and connected to the build environment, thus satisfying build dependencies for packages from subsequent lines. If a package version is already available in the connected repositories, a bin-nmu rebuild is automatically triggered. By default, the local `repository` and the log file `simplebuilder.log` will be located in `/tmp/workspace`. The build logs for a specific package are located in the repository and have the `.log` extension.

## Build from a single .dsc file
`echo "https://example.com/package.dsc" | simplebuilder`

## Build from a Git repository
`echo "https://github.com/user/repo.git" | simplebuilder`

## Build from multiple sources
```
http://deb.debian.org/debian/pool/main/h/hello/hello_2.10-3.dsc
https://salsa.debian.org/debian/runit.git
https://deb.debian.org/debian/pool/main/b/bcel/bcel_6.10.0-1.dsc
http://deb.debian.org/debian/pool/main/c/cowsay/cowsay_3.03+dfsg2-8.dsc
http://deb.debian.org/debian/pool/main/h/hello/hello_2.10-5.dsc
https://deb.debian.org/debian/pool/main/a/acct/acct_6.6.4-10.dsc
https://deb.debian.org/debian/pool/main/j/jq/jq_1.8.1-4.dsc
http://deb.debian.org/debian/pool/main/h/htop/htop_3.2.2-2.dsc
https://salsa.debian.org/debian/dash.git
http://ftp.debian.org/debian/pool/main/libs/libsepol/libsepol2_3.8.1-1_amd64.deb
http://deb.debian.org/debian/pool/main/libs/libselinux/libselinux_3.8.1-1.dsc
http://deb.debian.org/debian/pool/main/m/miller/miller_6.13.0-1.dsc
http://deb.debian.org/debian/pool/main/f/figlet/figlet_2.2.5-3.1.dsc
https://deb.debian.org/debian/pool/main/h/hello-traditional/hello-traditional_2.10-6.dsc
```

## Rebuid with suffix

`cat <file> | simplebuilder --suffix="+ubuntu1"`

## Docker build
`docker build -f simplebuilder/Dockerfile --build-arg BASE_IMAGE=debian:12 -t my-builder:debian-12`
or
`docker build -f simplebuilder/Dockerfile --build-arg BASE_IMAGE=debian:13 -t my-builder:debian-13`

## Docker run
```
docker run -it --rm \
  -v $(pwd)/repository:/workspace/repository \
  debian-pkg-builder \
  bash -c "cat urls.txt | python3 simplebuilder.py"
```
