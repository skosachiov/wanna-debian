# wanna-debian

## predose

Pre-dose is a small set of Python and Bash scripts designed for analyzing and backporting Debian packages from
newer releases (e.g., Sid) to older stable versions (e.g., Trixie or Bookworm).

readme: [docs/predose/index.md](docs/predose/index.md)

## distrotracker

Distribution package tracking and dependency resolution tool for Debian. Distrotracker helps track packages across Debian distributions and find minimum versions that satisfy dependencies. It's particularly useful for backporting and dependency resolution.

readme: [docs/distrotracker/index.md](docs/distrotracker/index.md)

## simplebuilder

The Simple Debian package builder handles different source types based on URL patterns provided. The build task is received via stdin. Each line of the task is a link to a Debian package or its source code. After building or downloading each package, the artifacts are placed in a local repository and connected to the build environment, thus satisfying build dependencies for packages from subsequent lines. If a package version is already available in the connected repositories, a bin-nmu rebuild is automatically triggered.

readme: [docs/simplebuilder/index.md](docs/simplebuilder/index.md)

## python deps

`sudo apt install python3-pip python3-apt python3-requests python3-debian`

## rootless userspace install from git

`pip install --user --break-system-packages git+https://.../wanna-debian.git`

or

`pip install --user --break-system-packages git+ssh://git@.../wanna-debian.git`

```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## upgrade

`pip install --upgrade --user --break-system-packages git+https://.../wanna-debian.git`

or

`pip install --upgrade --user --break-system-packages git+ssh://git@.../wanna-debian.git`

## uninstall

`pip uninstall -y --break-system-packages wanna-debian`
