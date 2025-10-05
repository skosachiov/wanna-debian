# distrotracker

Distribution package tracking and dependency resolution tool for Debian. `distrotracker` helps track packages across Debian distributions and find minimum versions that satisfy dependencies. It's particularly useful for backporting and dependency resolution.

## update metadata

`distrotracker --base-url http://deb.debian.org/debian/`

## search for the minimum version that satisfies dependencies

`echo 'libpython3.13 (>= 3.13.0~rc3)' | distrotracker --find`

or

`cat dose-unsat.list | distrotracker --find`

or dose-unsat.list example:
```
libx509-ocaml-dev (>= 1.0.0)
libduration-ocaml-dev
librust-gix-fs-0.12+default-dev (>= 0.12.1-~~)
libkdf-ocaml-dev-gjix7
librandomconv-ocaml-dev (>= 0.2)
```

```
cat dose-unsat.list | distrotracker --find --arch binary-amd64
cat dose-unsat.list | distrotracker --find --arch source
cat dose-unsat.list | distrotracker --find --arch binary-amd64 binary-arm64 --dist trixie sid
```

or backport.list example:
```
libx509-ocaml-dev=1.0.0
librust-gix-fs-0.12+default-dev=0.12.1
librandomconv-ocaml-dev=0.2
```

`cat backport.list | sed 's/=/ (>= /;s/$/)/' | distrotracker --find --briefly`

```
echo 'libpython3.13' | distrotracker --find | jq -c -r '.[] | "Package: \(.package), Version: \(.version)"'
```

## simple search with grep-dctrl 

```
find metadata/ -name Packages -type f -exec sh -c 'echo {} | cut -f 3,4 -d\/; grep-dctrl -n -s Package,Version,Section -P "" {} \
    | tr -s "\n" | paste -d = - - - | sed "s/^/    /" | grep -h " gnome-shell=" ' \;
