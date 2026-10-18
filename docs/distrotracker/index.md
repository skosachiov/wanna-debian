# distrotracker

Distribution package tracking and dependency resolution tool for Debian. `distrotracker` helps track packages across Debian distributions and find the minimum versions that satisfy dependencies. It is particularly useful for backporting and dependency resolution.

## update metadata

The default metadata local directory is `metadata`, and the default components are `main`, `main/debian-installer`, `contrib`, `non-free`, `non-free-firmware`.

`distrotracker --update-only --base-url http://deb.debian.org/debian/ --local-dir metadata-debian`

For Debian derivatives such as Ubuntu, you must use an explicit list of components, for example `main`, `main/debian-installer`, `multiverse`, `restricted`, `universe`:

`distrotracker --update-only --base-url http://us.archive.ubuntu.com/ubuntu/ --local-dir metadata-ubuntu --dist resolute noble --comp main main/debian-installer multiverse restricted universe`

## simple 'grep-like' search

`distrotracker --all --grep 'nvidia[^,]*?570'--dist trixie --build binary-amd64`

## search for versions that satisfy dependencies

### read one package from stdin

`echo 'openssh-server (>= 1:10.5p1-1ubuntu3)' | distrotracker --hold --local-dir metadata-ubuntu`

### read a list from stdin

`cat dose-unsat.list | distrotracker`

dose-unsat.list example:
```
libx509-ocaml-dev (>= 1.0.0)
libduration-ocaml-dev
librust-gix-fs-0.12+default-dev (>= 0.12.1-~~)
libkdf-ocaml-dev-gjix7
librandomconv-ocaml-dev (>= 0.2)
```

```
cat dose-unsat.list | distrotracker --build binary-amd64
cat dose-unsat.list | distrotracker --build source
cat dose-unsat.list | distrotracker --build binary-amd64 binary-arm64 --dist trixie sid
```

Or a backport.list example:
```
libx509-ocaml-dev=1.0.0
librust-gix-fs-0.12+default-dev=0.12.1
librandomconv-ocaml-dev=0.2
```

`cat backport.list | sed 's/=/ (>= /;s/$/)/' | distrotracker --briefly`

```
echo 'libpython3.13' | distrotracker | jq -c -r '.[] | "Package: \(.package), Version: \(.version)"'
```

## find packages built for only one of the two architectures

```
export DIST="rc-buggy"; distrotracker --all --dist $DIST --build binary-amd64 |  jq -c -r '.[] | "\(.source) (= \(.source_version))"' | sort -u | distrotracker --hold --source --dist $DIST | jq -c -r '.[] | select(.dist == env.DIST and .build == "source") | select(.arch | contains("all") and (contains("any") or contains("linux-any") or contains("amd64"))) | "\(.source) (= \(.source_version))"' | distrotracker --hold --source --dist $DIST --build binary-amd64 | jq -c -r '.[] | select(.dist == env.DIST) | "\(.source) \(.arch)"' | sort -u | cut -f 1 -d ' ' | uniq -c | sort -r
```

## j2 transformation

File convert.j2:
```
{% for item in input_list %}
EXAMPLE,{{ item.source }}={{ item.source_version}},{{ item.filename }},{{ item.dist }},EXAMPLE
{%- endfor %}
```

`echo vim | distrotracker --hold | jq ''{"input_list": .} | j2 -f json convert.j2 -`

File groupby.j2:
```
{% for dist, items in input_list|groupby('dist') %}
EXAMPLE,{{ dist }}, {% for item in items %} {{item.source}}={{item.source_version}} {%- endfor %}
{%- endfor %}
```

`echo vim | distrotracker --hold | jq ''{"input_list": .} | j2 -f json groupby.j2 -`

## simple search with grep-dctrl

```
find metadata/ -name Packages -type f -exec sh -c 'echo {} | cut -f 3,4 -d\/; grep-dctrl -n -s Package,Version,Section -P "" {} \
    | tr -s "\n" | paste -d = - - - | sed "s/^/    /" | grep -h " gnome-shell=" ' \;
```

## extract last-modified from pool

```
echo vim | distrotracker --hold --local-dir metadata-debian --dist trixie --source --build binary-amd64 \
| jq -c -r '.[] | "https://ftp.debian.org/debian/\(.filename)"' \
| xargs -I {} sh -c 'url="{}"; echo "$(basename "$url" | sed "s/_.*//") \
$(curl -sI "$url" | grep -i last-modified | sed "s/^last-modified: //I" | date -f - +%Y-%m-%dT%H:%M:%S%z)"'
```

## git diff

metadata/.gitignore

```
*
!*/
!*.json
```

`where true; do git -C metadata add --all; git -C metadata commit -m auto; distrotracker -u; sleep 1h; done`

`git -C metadata diff`

`git -C metadata diff --unified=0 | grep '^\+  {' | sed 's/^\+  //;s/,$//' | jq -r -c -n '[inputs] | .[] | "\(.dist)\t\(.package)=\(.version)\t\(.build)"'`
