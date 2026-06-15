#!/usr/bin/env python3

import re
import argparse
import sys
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set, Any

import apt_pkg
from toposort import Node, StableTopoSort

apt_pkg.init_system()


@dataclass
class PackageEntry:
    package: str
    version: str
    block: str
    depends: List[str]
    source: str
    source_version: str


PkgKey = Tuple[str, str]


def _format_key(key: PkgKey, add_version: bool = True) -> str:
    if len(key) < 2: return ""
    if add_version:
        return f'{key[0]}{"=" if key[1] != "" else ""}{key[1]}'
    else:
        return key[0]


class Metadata:
    """Parsed Debian repository metadata (Sources or Packages)."""

    def __init__(self) -> None:
        self.is_bin: bool = True
        self.packages: Dict[PkgKey, PackageEntry] = {}
        self.src_dict: Dict[str, str] = {}
        self.bin_dict: Dict[PkgKey, List[str]] = {}
        self.prov_dict: Dict[str, str] = {}
        self.latest_index: Dict[str, PkgKey] = {}
        self.latest_src: Dict[str, PkgKey] = {}

    @classmethod
    def from_file(cls, filepath: str) -> 'Metadata':
        meta = cls()
        meta._parse(filepath)
        return meta

    def _parse(self, filepath: str) -> None:

        with open(filepath, 'rt', encoding='utf-8') as f:
            content = f.read()
            blocks = re.split(r'\n\n+', content.strip())

        for block in blocks:
            if not block.strip():
                continue

            pkg_name = version = source = source_version = None
            depends: List[str] = []
            bin_pkgs: List[str] = []
            block_list: List[str] = []

            for line in block.splitlines():
                if block_list and block_list[-1].endswith(',') and line and line[0].isspace():
                    block_list[-1] += line.rstrip()
                elif line:
                    block_list.append(line.rstrip())

            for line in block_list:
                if not line or line[0].isspace() or ':' not in line:
                    continue

                key, value = line.split(':', 1)
                value = value.strip()

                if key == 'Package':
                    pkg_name = value
                elif key == 'Binary':
                    self.is_bin = False
                    bin_pkgs = [(p.strip(), '') for p in value.split(',')]
                elif key == 'Source':
                    source_line = value.strip().split()
                    if len(source_line) > 0:
                        source = source_line[0]
                        if len(source_line) > 1: source_version = re.findall(r'\((.*?)\)', source_line[1])[0]
                elif key == 'Provides':
                    prov_pkgs = [p.strip().split()[0] for p in value.split(',')]
                    for p in prov_pkgs:
                        self.prov_dict[p] = pkg_name
                elif key == 'Version':
                    version = value
                elif key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch',
                             'Depends', 'Pre-Depends'):
                    deps_pkgs = [p.strip() for p in value.split(',') if p.strip()]
                    for p in deps_pkgs:
                        dep_name = p.split()[0].split(":")[0]
                        if dep_name == pkg_name:
                            logging.debug(
                                f'Package depends on itself, excluded: {pkg_name}'
                            )
                            continue
                        if any(profile in p for profile in ("<!nocheck>", "<!nodoc>")):
                            logging.debug(
                                f'Dependency with profiles, excluded: {pkg_name}: {p}'
                            )
                            continue
                        depends.append(dep_name)

            if pkg_name is None:
                continue

            if source is None: source = pkg_name
            if source_version is None: source_version = version
            pkg_key = (pkg_name, version)
            src_key = (source, source_version)

            if pkg_key in self.packages:
                logging.warning(f'Duplicate package detected: {pkg_key}')
                continue

            if self.is_bin:
                bin_pkgs = [pkg_key]

            if src_key not in self.bin_dict:
                self.bin_dict[src_key] = bin_pkgs
            else:
                self.bin_dict[src_key].extend(bin_pkgs)
            
            for p in bin_pkgs:
                self.src_dict[p] = src_key

            self.packages[pkg_key] = PackageEntry(
                package=pkg_name,
                version=version,
                block=block,
                depends=depends,
                source=source,
                source_version=source_version,
            )

            latest = self.latest_index.get(pkg_name)
            if latest is None or apt_pkg.version_compare(version, latest[1]) > 0:
                self.latest_index[pkg_name] = pkg_key

            latest = self.latest_src.get(source)
            if latest is None or apt_pkg.version_compare(source_version, latest[1]) > 0:
                self.latest_src[source] = src_key

        logging.debug(f'Parsed {len(self.packages)} packages from {filepath}')

    def resolve_pkg_name(self, pkg_name: str) -> Optional[PkgKey]:
        found = self.latest_index.get(pkg_name)
        if found is not None:
            return found
        if pkg_name in self.src_dict:
            return self.latest_index.get(self.src_dict[pkg_name])
        if pkg_name in self.prov_dict:
            provider = self.prov_dict[pkg_name]
            if provider in self.src_dict:
                return self.latest_index.get(self.src_dict[provider])
            found = self.latest_index.get(provider)
            if found is not None:
                return found
            logging.error(f'Cannot resolve provided package: {pkg_name}')
            return None
        logging.warning(f'Package not found: {pkg_name}')
        return None

    def _resolve_key(self, pkg_key: PkgKey) -> Optional[PkgKey]:
        name, version = pkg_key
        if version:
            if pkg_key in self.packages:
                return pkg_key
            logging.error(f'Package not found: {pkg_key}')
            return None
        found = self.latest_index.get(name)
        if found is not None:
            return found
        return pkg_key

    def leave_latest(self):
        to_delete = []
        for p in self.packages:
            if p not in self.latest_index.values():
                to_delete.append(p)
        for p in to_delete:
            del self.packages[p]

    def resolve_src(self, pkg_key: Optional[PkgKey], add_version: bool = False) -> str:
        if self.is_bin:
            if pkg_key[1] == "":
                pkg_key = self.latest_index.get(pkg_key[0], "")
        return _format_key(self.src_dict.get(pkg_key, ""), add_version)

    def resolve_bin(self, pkg_key: Optional[PkgKey], add_version: bool = False) -> str:
        if pkg_key[1] == "":
            pkg_key = self.latest_src.get(pkg_key[0])
        out = '\n'.join(_format_key(k, add_version) for k in self.bin_dict.get(pkg_key, []))     
        return out

    def resolve_group(self, pkg_key: Optional[PkgKey], add_version: bool = False) -> str:
        if self.is_bin:
            if pkg_key[1] == "":
                pkg_key = self.latest_index.get(pkg_key[0], "")
        for bin_pkgs in self.bin_dict.values():
            if pkg_key in bin_pkgs:
                return '\n'.join(_format_key(k, add_version) for k in bin_pkgs)
        return ""

    def add_version(self, line_left_side: str) -> str:
        parts = line_left_side.split('=')
        name = parts[0]
        ver = parts[1] if len(parts) > 1 else ''
        for k, entry in self.packages.items():
            if k[0] == name:
                if ver and k[1] != ver:
                    continue
                return f'{k[0]}={entry.version}'
        logging.error(f'Package not found: {line_left_side}')
        return ''

    def depends(self, pkg_key: Optional[PkgKey], depth: int, depends_set: Dict) -> Tuple[Dict, str]:
        if pkg_key is not None:
            depends_set[pkg_key] = None
            for i in range(depth):
                before = len(depends_set)
                for p in dict(depends_set).keys():
                    ps = self.resolve_pkg_name(p[0])
                    if ps and ps in self.packages:
                        for pd in self.packages[ps].depends:
                            pds = self.resolve_pkg_name(pd)
                            if pds:
                                depends_set[pds] = None
                if before == len(depends_set):
                    logging.info(f'Dependency search done at iteration {i + 1}')
                    break
            else:
                logging.warning(f'Dependency search did not reach leaves: {depth}')
        out = '\n'.join(_format_key(k, False) for k in depends_set.keys())
        return depends_set, out

    def rdepends(self, name: str) -> str:
        out: List[str] = []
        for p in self.packages:
            if name in self.packages[p].depends:
                out.append(_format_key(p, False))
        return '\n'.join(out)

    def remove(self, pkg_key: Optional[PkgKey]) -> str:
        if pkg_key is not None:
            if pkg_key in self.packages:
                del self.packages[pkg_key]
                logging.info(f'Removed: {pkg_key}')
            else:
                logging.error(f'Not present: {pkg_key}')
        return ''

    def backport(self, pkg_key: Optional[PkgKey], target: 'Metadata', add_missing: bool = False) -> bool:
        if pkg_key not in self.packages:
            logging.error(f'No package in origin: {pkg_key}')
            return False
        if pkg_key[0] not in target.latest_index.keys():
            target.packages[pkg_key] = self.packages[pkg_key]
            logging.info(f'Add to target: {pkg_key}')
            return True
        if not add_missing:
            target.packages[pkg_key] = self.packages[pkg_key]
            logging.info(f'Replace in target: {pkg_key}={self.packages[pkg_key].version}')
            return True
        logging.warning(f'Already in target: {pkg_key}')
        return False

    def output_blocks(self) -> None:
        for entry in self.packages.values():
            print(entry.block)
            print()

    def toposort(self, packages_set: Set[PkgKey], dot_file: Optional[str] = None) -> str:
        graph: Dict = {}
        for p in packages_set:
            if p not in graph:
                graph[p] = set()
            if p not in self.packages:
                continue
            for d in self.packages[p].depends:
                pk = self.resolve_pkg_name(d.split()[0])
                if pk and pk in packages_set:
                    graph[p].add(pk)
                    if pk not in graph:
                        graph[pk] = set()

        if dot_file:
            with open(dot_file, 'w') as f:
                f.write(dict_to_dot(graph))

        rev = {n: set() for n in graph}
        for n, nb in graph.items():
            for nb2 in nb:
                rev[nb2].add(n)
        nodes = {name: Node(str(name)) for name in rev}
        edge_count = 0
        for name, edges in rev.items():
            node = nodes[name]
            edge_count += len(edges)
            for en in edges:
                node.edges.append(nodes[en])
        nlist = list(nodes.values())
        logging.debug(f'Toposort started, edges: {edge_count}')
        sl = StableTopoSort.stable_topo_sort(nlist)
        tl = [(level, node.name) for level, node in sl]
        return '\n'.join(str(t) for t in sorted(tl))


def reverse_graph(graph: Dict) -> Dict:
    rev: Dict = {n: set() for n in graph}
    for n, nb in graph.items():
        for nb2 in nb:
            rev[nb2].add(n)
    return rev


def dict_to_dot(d: Dict, graph_name: str = 'G') -> str:
    lines = [f"digraph {graph_name} {{"]
    for key, values in d.items():
        label = _format_key(key)
        lines.append(f'    "{label}";')
        for value in values:
            vlabel = _format_key(value, False)
            lines.append(f'    "{vlabel}";')
            lines.append(f'    "{label}" -> "{vlabel}";')
    lines.append("}")
    return '\n'.join(lines)


class PreDoseApp:
    """Main application class for pre-dose."""

    def __init__(self) -> None:
        self.origin_meta: Optional[Metadata] = None
        self.target_meta: Optional[Metadata] = None
        self.args: Any = None

    def configure_logging(self) -> None:
        handlers = []
        if self.args.log_file:
            handlers.append(logging.FileHandler(self.args.log_file))
        else:
            handlers.append(logging.StreamHandler())
        logging.basicConfig(
            handlers=handlers,
            level=getattr(logging, self.args.log_level),
            format='%(asctime)s %(levelname)s %(message)s',
        )

    def parse_args(self, argv: Optional[List[str]] = None) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description='Pre-dose: targeted substitution of package information '
                        'from an origin repository to a target repository.',
        )
        parser.add_argument('origin_repo', metavar='ORIGIN_REPO', nargs='?',
                            help='newer repository Packages/Sources')
        parser.add_argument('target_repo', metavar='TARGET_REPO',
                            help='older repository Packages/Sources')
        parser.add_argument('-m', '--add-missing', action='store_true',
                            help='add missing packages, do not change versions')
        parser.add_argument('-r', '--remove', action='store_true',
                            help='remove packages instead of replacing or adding')
        parser.add_argument('-p', '--provide', type=str, metavar='PATH',
                            help='path to binary Packages metadata for source implantation')
        parser.add_argument('-e', '--depends', type=int, metavar='DEPTH',
                            help='print repository package dependencies and exit')
        parser.add_argument('-n', '--rdepends', action='store_true',
                            help='determine which package depends on a given dependency and exit')
        parser.add_argument('-s', '--resolve-src', action='store_true',
                            help='resolve source code package names and exit')
        parser.add_argument('-b', '--resolve-bin', action='store_true',
                            help='resolve binary package names by source metadata and exit')
        parser.add_argument('-o', '--resolve-group', action='store_true',
                            help='resolve target binary group and exit')
        parser.add_argument('-t', '--topo-sort', action='store_true',
                            help='perform topological sort and exit')
        parser.add_argument('-c', '--latest', action='store_true',
                            help='leave only the latest versions of packages')
        parser.add_argument('-g', '--dot', type=str,
                            help='save toposort graph to dot file')
        parser.add_argument('-a', '--add-version', action='store_true',
                            help='add version to output for resolve operations and exit')
        parser.add_argument('-l', '--log-level', default='INFO',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                            help='set the logging level (default: INFO)')
        parser.add_argument('--log-file',
                            help='save logs to file (default: stderr)')
        self.args = parser.parse_args(argv)
        return self.args

    def _only_one(self) -> bool:
        return any((
            self.args.remove, self.args.resolve_bin, self.args.resolve_src,
            self.args.resolve_group, self.args.depends, self.args.rdepends,
            self.args.topo_sort,
        ))

    def _resolve_name(self, name: str) -> Optional[PkgKey]:
        if self.origin_meta:
            found = self.origin_meta.latest_index.get(name)
            if found:
                return found
        return None

    def _parse_input_line(self, line: str) -> Tuple[Optional[PkgKey], List[str]]:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            return None, []
        parts = stripped.split('=')
        name = parts[0]
        version = parts[1] if len(parts) > 1 else ''
        if version:
            return (name, version), parts
        resolved = self._resolve_name(name)
        if resolved is None:
            return None, parts
        return resolved, parts

    def run(self, argv: Optional[List[str]] = None) -> None:
        self.parse_args(argv)
        self.configure_logging()
        logging.info(f'Pre-dose started with args: {self.args}')

        only_one = self._only_one()

        if only_one and self.args.origin_repo is not None:
            argparse.ArgumentParser().error("option does not require ORIGIN_REPO")

        path = self.args.origin_repo if not only_one else self.args.target_repo
        self.origin_meta = Metadata.from_file(path)
        if self.args.latest:
            self.origin_meta.leave_latest()
        if not only_one:
            self.target_meta = Metadata.from_file(self.args.target_repo)
            if self.args.latest:
                self.target_meta.leave_latest()
        if self.args.provide:
            provide_meta = Metadata.from_file(self.args.provide)
            for k in provide_meta.prov_dict:
                self.origin_meta.prov_dict[k] = provide_meta.prov_dict[k]

        packages_set: Set[PkgKey] = set()
        depends_set: Dict = {}
        input_lines: List[List[str]] = []

        for line in sys.stdin:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            parts = stripped.split('=')
            name = parts[0]
            version = parts[1] if len(parts) > 1 else ''

            pkg_key = (name, version)

            packages_set.add(pkg_key)
            input_lines.append(parts)

            result = None

            if self.args.resolve_src:
                result = self.origin_meta.resolve_src(pkg_key, self.args.add_version)
            elif self.args.resolve_bin:
                result = self.origin_meta.resolve_bin(pkg_key, self.args.add_version)
            elif self.args.resolve_group:
                result = self.origin_meta.resolve_group(pkg_key, self.args.add_version)
            elif self.args.depends:
                depends_set, result = self.origin_meta.depends(
                    pkg_key, self.args.depends, depends_set,
                )
            elif self.args.rdepends:
                result = self.origin_meta.rdepends(name)
            elif self.args.topo_sort:
                pass
            elif self.args.remove:
                self.origin_meta.remove(pkg_key)
            elif self.args.add_version:
                result = self.origin_meta.add_version(parts[0])
            elif pkg_key is not None:
                tgt = self.target_meta if not only_one else self.origin_meta
                self.origin_meta.backport(pkg_key, tgt, self.args.add_missing)
            else:
                logging.error(f'Unresolved package: {line.strip()}')

            if result:
                print(result)

        if self.args.topo_sort:
            tgt = self.target_meta if not only_one else self.origin_meta
            result = tgt.toposort(packages_set, self.args.dot)
            if result:
                print(result)

        if not any((
            self.args.add_version, self.args.depends, self.args.resolve_src,
            self.args.resolve_bin, self.args.rdepends, self.args.resolve_group,
            self.args.topo_sort,
        )):
            if self.args.remove:
                self.origin_meta.output_blocks()
            else:
                src = self.origin_meta if self._only_one() else self.target_meta
                if src:
                    src.output_blocks()

        logging.debug(f'Pre-dose finished, input lines: {input_lines}')


def main() -> None:
    app = PreDoseApp()
    app.run()


if __name__ == '__main__':
    main()
