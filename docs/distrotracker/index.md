# distrotracker

Distribution package tracking and dependency resolution tool for Debian. `distrotracker` helps track packages across Debian distributions and find minimum versions that satisfy dependencies. It's particularly useful for backporting and dependency resolution.

## update metadata

`distrotracker --base-url http://deb.debian.org/debian/`

or

`distrotracker --base-url http://ru.archive.ubuntu.com/ubuntu/ --local-dir metadata-ubuntu --comp main universe`


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
cat dose-unsat.list | distrotracker --find --build binary-amd64
cat dose-unsat.list | distrotracker --find --build source
cat dose-unsat.list | distrotracker --find --build binary-amd64 binary-arm64 --dist trixie sid
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

## find packages with only one of the two architectures built

```
export DIST="rc-buggy"; cat metadata/index.json | jq -c -r '.[] | select(.dist == env.DIST and .build == "binary-amd64") | "\(.source) (= \(.source_version))"' | sort -u | distrotracker --find --hold --source --dist $DIST | jq -c -r '.[] | select(.dist == env.DIST and .build == "source") | select(.arch | contains("all") and (contains("any") or contains("linux-any") or contains("amd64"))) | "\(.source) (= \(.source_version))"' | distrotracker --find --hold --source --dist $DIST --build binary-amd64 | jq -c -r '.[] | select(.dist == env.DIST) | "\(.source) \(.arch)"' | sort -u | cut -f 1 -d ' ' | uniq -c | sort -r
```

## j2 transformation

file convert.j2:
```
{% for item in input_list %}
EXAMPLE,{{ item.source }}={{ item.source_version}},{{ item.filename }},{{ item.dist }},EXAMPLE
{%- endfor %}
```

`echo vim | distrotracker --find --hold | jq ''{"input_list": .} | j2 -f json convert.j2 -`

file groupby.j2:
```
{% for dist, items in input_list|groupby('dist') %}
EXAMPLE,{{ dist }}, {% for item in items %} {{item.source}}={{item.source_version}} {%- endfor %}
{%- endfor %}
```

`echo vim | distrotracker --find --hold | jq ''{"input_list": .} | j2 -f json groupby.j2 -`

## simple search with grep-dctrl

```
find metadata/ -name Packages -type f -exec sh -c 'echo {} | cut -f 3,4 -d\/; grep-dctrl -n -s Package,Version,Section -P "" {} \
    | tr -s "\n" | paste -d = - - - | sed "s/^/    /" | grep -h " gnome-shell=" ' \;
