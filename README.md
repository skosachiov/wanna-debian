# wanna-debian

## predose

Pre-dose is a small set of Python and Bash scripts designed for analyzing and backporting Debian packages from
newer releases (e.g., Sid) to older stable versions (e.g., Trixie or Bookworm).

readme: [docs/predose/index.md](docs/predose/index.md)

## distrotracker

Distribution package tracking and dependency resolution tool for Debian. Distrotracker helps track packages across Debian distributions and find minimum versions that satisfy dependencies. It's particularly useful for backporting and dependency resolution.

readme: [docs/distrotracker/index.md](docs/distrotracker/index.md)

## python deps

`apt install python3-apt python3-requests python3-debian`

## rootless userspace install

`pip install --user --break-system-packages  git+https://.../wanna-debian.git`
or
`pip install --user --break-system-packages  git+ssh://.../wanna-debian.git`

```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## upgrade

`pip install --upgrade --user --break-system-packages  git+https://.../wanna-debian.git`
or
`pip install --upgrade --user --break-system-packages  git+ssh://.../wanna-debian.git`

## uninstall

`pip uninstall -y --break-system-packages  wanna-debian`
