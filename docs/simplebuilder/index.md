# Build from a single .dsc file
echo "https://example.com/package.dsc" | python3 build-packages.py

# Build from a Git repository
echo "https://github.com/user/repo.git" | python3 build-packages.py

# Build from multiple sources
echo -e "https://github.com/user/repo.git\nhttps://example.com/package.dsc" | python3 build-packages.py

docker run -it --rm \
  -v $(pwd)/repository:/workspace/repository \
  debian-pkg-builder \
  bash -c "cat urls.txt | python3 build-packages.py"