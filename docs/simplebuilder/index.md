# Build from a single .dsc file
`echo "https://example.com/package.dsc" | simplebuilder`

# Build from a Git repository
`echo "https://github.com/user/repo.git" | simplebuilder`

# Build from multiple sources
```
https://github.com/user/repo.git # comment
https://example.com/pkg-1.2.3.dsc
https://example.com/chromium-140.dsc # rebuild with b1
https://example.com/package.deb # no reprepro before copy
file:///home/user/abc-1.2.3.deb #
file:///home/user/package-1.2.3.deb
https://example.com/package.dsc
```

# Docker run
```
docker run -it --rm \
  -v $(pwd)/repository:/workspace/repository \
  debian-pkg-builder \
  bash -c "cat urls.txt | python3 simplebuilder.py"
```
