#!/usr/bin/env python3

import re
import argparse
import sys
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set, Any, NamedTuple

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


class PkgKey(NamedTuple):
    package: str
    version: str

    def __str__(self):
        return f'{self.package}{"=" if self.version != "" else ""}{self.version}'


def _format_key(key: PkgKey, add_version: bool = True) -> str:
    if not isinstance(key, PkgKey): return ""
    if add_version:
        return f'{key.package}{"=" if key.version != "" else ""}{key.version}'
    else:
        return key.package


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

            package = version = source = source_version = None
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
                    package = value
                elif key == 'Binary':
                    self.is_bin = False
                    bin_pkgs = [PkgKey(p.strip(), '') for p in value.split(',')]
                elif key == 'Source':
                    source_line = value.strip().split()
                    if len(source_line) > 0:
                        source = source_line[0]
                        if len(source_line) > 1: source_version = re.findall(r'\((.*?)\)', source_line[1])[0]
                elif key == 'Provides':
                    prov_pkgs = [p.strip().split()[0] for p in value.split(',')]
                    for p in prov_pkgs:
                        self.prov_dict[p] = package
                elif key == 'Version':
                    version = value
                elif key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch',
                             'Depends', 'Pre-Depends'):
                    deps_pkgs = [p.strip() for p in value.split(',') if p.strip()]
                    for p in deps_pkgs:
                        dep_name = p.split()[0].split(":")[0]
                        if dep_name == package:
                            logging.debug(
                                f'Package depends on itself, excluded: {package}'
                            )
                            continue
                        if any(profile in p for profile in ("<!nocheck>", "<!nodoc>")):
                            logging.debug(
                                f'Dependency with profiles, excluded: {package}: {p}'
                            )
                            continue
                        depends.append(dep_name)

            if package is None:
                continue

            if source is None: source = package
            if source_version is None: source_version = version
            pkg_key = PkgKey(package, version)
            src_key = PkgKey(source, source_version)

            if self.is_bin: self.prov_dict[package] = package

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
                package=package,
                version=version,
                block=block,
                depends=depends,
                source=source,
                source_version=source_version,
            )

            latest = self.latest_index.get(package)
            if latest is None or apt_pkg.version_compare(version, latest.version) > 0:
                self.latest_index[package] = pkg_key

            latest = self.latest_src.get(source)
            if latest is None or apt_pkg.version_compare(source_version, latest.version) > 0:
                self.latest_src[source] = src_key

        logging.debug(f'Parsed {len(self.packages)} packages from {filepath}')

    def leave_latest(self):
        latest_set = set(self.latest_index.values())
        # Keep only packages whose key is in the latest_set
        self.packages = {k: v for k, v in self.packages.items() if k in latest_set}

    def resolve_src(self, pkg_key: Optional[PkgKey], add_version: bool = False) -> str:
        if self.is_bin:
            if pkg_key.version == "":
                pkg_key = self.latest_index.get(pkg_key.package, "")
        return _format_key(self.src_dict.get(pkg_key, ""), add_version)

    def resolve_bin(self, pkg_key: Optional[PkgKey], add_version: bool = False) -> str:
        if pkg_key.version == "":
            pkg_key = self.latest_src.get(pkg_key.package)
        out = '\n'.join(_format_key(k, add_version) for k in self.bin_dict.get(pkg_key, []))
        return out

    def resolve_group(self, pkg_key: Optional[PkgKey], add_version: bool = False) -> str:
        if self.is_bin:
            if pkg_key.version == "":
                pkg_key = self.latest_index.get(pkg_key.package, "")
        for bin_pkgs in self.bin_dict.values():
            if pkg_key in bin_pkgs:
                return '\n'.join(_format_key(k, add_version) for k in bin_pkgs)
        return ""

    def add_version(self, line_left_side: str) -> str:
        parts = line_left_side.split('=')
        name = parts[0]
        ver = parts[1] if len(parts) > 1 else ''
        for k, entry in self.packages.items():
            if k.package == name:
                if ver and k.version != ver:
                    continue
                return f'{k.package}={entry.version}'
        logging.error(f'Package not found: {line_left_side}')
        return ''

    def depends(self, package: str, depth: int):
        depends_set = set()
        print("D", package)
        depends_set.add(package.package)
        for i in range(depth):
            before = len(depends_set)
            for d in [self.packages[self.latest_index[package]].depends for package in depends_set]:
                print("D", d)
                depends_set.update(d)
            if before == len(depends_set):
                logging.info(f'Dependency search done at iteration {i + 1}')
                break
        else:
            logging.warning(f'Dependency search did not reach leaves: {depth}')

        return '\n'.join(depends_set)

    def rdepends(self, name: str) -> str:
        out: List[str] = []
        for p in self.packages:
            if name in self.packages[p].depends:
                out.append(_format_key(p, False))
        return '\n'.join(out)

    def remove(self, pkg_key: Optional[PkgKey]) -> bool:
        key = pkg_key
        if not key.version:
            key = self.latest_index.get(pkg_key.package, "")
        if key is not None:
            if key in self.packages:
                del self.packages[key]
                logging.info(f'Removed: {key}')
                return True
            else:
                logging.error(f'Not present: {pkg_key}')
        return False

    def backport(self, pkg_key: Optional[PkgKey], target: 'Metadata') -> bool:
        if not pkg_key.version:
            pkg_key = self.latest_index.get(pkg_key.package, PkgKey(pkg_key.package, ""))
        if pkg_key not in self.packages:
            logging.error(f'No package in origin: {pkg_key}')
            return False
        if pkg_key in target.packages.keys():
            logging.warning(f'Already in target: {pkg_key}')
            return False
        if pkg_key not in target.latest_index.keys():
            target.packages[pkg_key] = self.packages[pkg_key]
            latest = target.latest_index.get(pkg_key.package)
            if latest is None or apt_pkg.version_compare(pkg_key.version, latest.version) > 0:
                target.latest_index[pkg_key.package] = pkg_key
            logging.info(f'Add to target: {pkg_key}')
            return True
        return False

    def output_blocks(self) -> None:
        for entry in self.packages.values():
            print(entry.block)
            print()

    def toposort(self, packages_set: Set[PkgKey], dot_file: Optional[str] = None) -> str:
        graph: Dict = {}
        # Build dependency graph
        for p in packages_set:
            if p.package not in graph: graph[p.package] = set()
            for d in self.packages[self.latest_index.get(p.package)].depends:
                package = self.src_dict.get(PkgKey(d, ''))
                if package is None: continue
                if PkgKey(package.package, '') in packages_set:
                    graph[p.package].add(package.package)
                    if package.package not in graph: graph[package.package] = set()
        # Save graph to dot file
        if dot_file:
            with open(dot_file, 'w') as f:
                f.write(dict_to_dot(graph))
        # Prepare graph for topological sort
        graph_dict = reverse_graph(graph)
        nodes = {name: Node(name) for name in graph_dict}
        edges_counter = 0
        for name, edges in graph_dict.items():
            node = nodes[name]
            edges_counter += len(edges)
            for edge_name in edges:
                node.edges.append(nodes[edge_name])
        nodes = list(nodes.values())
        logging.debug(f'Stable topological sort started, number of edges: {edges_counter}')
        # Perform and output topological sort
        sorted_nodes_with_levels = StableTopoSort.stable_topo_sort(nodes)
        tl = []
        for level, node in sorted_nodes_with_levels:
            tl.append((level, node.name))
        output_lines = [str(t) for t in sorted(tl)]
        return '\n'.join(output_lines)

def reverse_graph(graph: Dict) -> Dict:
    reversed_graph: Dict = {node: set() for node in graph}
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            reversed_graph[neighbor].add(node)
    return reversed_graph


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
            return PkgKey(name, version), parts
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
        if only_one:
            if self.args.latest:
                self.origin_meta.leave_latest()
        else:
            self.target_meta = Metadata.from_file(self.args.target_repo)
            if self.args.latest:
                self.target_meta.leave_latest()

        if self.args.provide:
            provide_meta = Metadata.from_file(self.args.provide)
            for k in provide_meta.prov_dict:
                self.origin_meta.prov_dict[k] = provide_meta.prov_dict[k]

        packages_set: Set[PkgKey] = set()
        input_lines: List[List[str]] = []

        for line in sys.stdin:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            parts = stripped.split('=')
            name = parts[0]
            version = parts[1] if len(parts) > 1 else ''

            pkg_key = PkgKey(name, version)

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
                result = self.origin_meta.depends(pkg_key, self.args.depends)
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
                self.origin_meta.backport(pkg_key, tgt)
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
                    if self.args.latest:
                        src.leave_latest()
                    src.output_blocks()

        logging.debug(f'Pre-dose finished, input lines: {input_lines}')


def main() -> None:
    app = PreDoseApp()
    app.run()


if __name__ == '__main__':
    main()
