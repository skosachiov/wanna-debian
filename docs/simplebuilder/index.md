# Build from a single .dsc file
`echo "https://example.com/package.dsc" | simplebuilder`

# Build from a Git repository
`echo "https://github.com/user/repo.git" | simplebuilder`

# Build from multiple sources
```
http://deb.debian.org/debian/pool/main/h/hello/hello_2.10-5.dsc
https://salsa.debian.org/debian/runit.git
https://deb.debian.org/debian/pool/main/a/acct/acct_6.6.4-10.dsc
https://deb.debian.org/debian/pool/main/h/hello/hello_2.10-3.dsc
https://deb.debian.org/debian/pool/main/j/jq/jq_1.8.1-4.dsc
http://ftp.debian.org/debian/pool/main/libs/libsepol/libsepol2_3.8.1-1_amd64.deb
http://deb.debian.org/debian/pool/main/libs/libselinux/libselinux_3.8.1-1.dsc
https://deb.debian.org/debian/pool/main/h/hello-traditional/hello-traditional_2.10-6.dsc
```

# Docker run
```
docker run -it --rm \
  -v $(pwd)/repository:/workspace/repository \
  debian-pkg-builder \
  bash -c "cat urls.txt | python3 simplebuilder.py"
```
