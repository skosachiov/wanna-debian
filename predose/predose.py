#!/usr/bin/env python3

import re, argparse, sys, logging
from toposort import *

import apt_pkg
apt_pkg.init_system()

# Parse package metadata from repository file
def parse_metadata(filepath, src_dict = None, prov_dict = None, bin_dict = None):
    packages = {}
    is_bin_metadata = True
    with open(filepath, 'rt', encoding='utf-8') as f:
        content = f.read()
        # Split into individual package blocks
        package_blocks = re.split(r'\n\n+', content.strip())
        for block in package_blocks:
            pkg_name = version = source = source_version = None
            depends = []
            block_list = []
            for line in block.splitlines():
                if len(block_list) > 0 and block_list[-1][-1] == ',' and line[0].isspace():
                    block_list[-1] += line.rstrip()
                else:
                    if line:
                        block_list.append(line.rstrip())
            for line in block_list:
                if not line or line[0].isspace(): continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    # Extract package name
                    if key == 'Package':
                        if pkg_name is not None:
                            logging.error(f'Duplicate stanza key: {key}: {value.strip()}')
                        pkg_name = value.strip()
                    # Build binary-to-source mapping for source metadata if requested
                    if key == 'Binary' and bin_dict is not None and src_dict is not None:
                        is_bin_metadata = False
                        if src_dict is not None:
                            bin_pkgs = [p.strip() for p in value.split(',')]
                            if bin_dict is not None: bin_dict[pkg_name] = bin_pkgs
                            for p in bin_pkgs:
                                src_dict[p] = pkg_name
                    # Build binary-to-source mapping for binary metadata if requested
                    if key == 'Source' and bin_dict is not None:
                        source_line = value.strip().split()
                        if len(source_line) > 0:
                            source = source_line[0]
                            if len(source_line) > 1: source_version = re.findall(r'\((.*?)\)', source_line[1])[0]
                        if source not in bin_dict:
                            bin_dict[source] = [pkg_name]
                        else:
                            bin_dict[source].append(pkg_name)
                    # Build provides mapping if requested
                    if key == 'Provides' and prov_dict is not None:
                        prov_pkgs = [p.strip().split()[0] for p in value.split(',')]
                        for p in prov_pkgs:
                            prov_dict[p] = pkg_name
                    # Extract version
                    if key == 'Version':
                        version = value.strip()
                    # Collect dependencies
                    if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends', 'Pre-Depends'):
                        deps_pkgs = [p.strip() for p in value.split(',') if p.strip()]
                        for p in deps_pkgs:
                            # Remove the dependency on yourself since the build stages are not taken into account
                            if p.split()[0].split(":")[0] == pkg_name:
                                logging.warning(f'Package depends on itself, '
                                    f'package name is excluded from dependencies: {pkg_name}')
                                continue
                            # Remove the dependency on some profiles
                            if any(profile in p for profile in ("<!nocheck>", "<!nodoc>")):
                                logging.debug(f'Dependency with profile restrictions, '
                                    f'package name is excluded from dependencies: {pkg_name}: {p}')
                                continue
                            depends.append(p.split()[0].split(":")[0])
            # Store package metadata if valid
            if pkg_name is not None:
                if pkg_name not in packages or apt_pkg.version_compare(version, packages[pkg_name]['version']) > 0:
                    if source is None:
                        source = pkg_name
                        if is_bin_metadata and bin_dict is not None:
                            if source not in bin_dict:
                                bin_dict[source] = [pkg_name]
                            else:
                                bin_dict[source].append(pkg_name)
                    if source_version is None: source_version = version
                    packages[pkg_name] = {'version': version, 'block': block, 'depends': depends, \
                        'source': source, 'source_version': source_version}
                else:
                    logging.warning(f'A new version package already in the list: {pkg_name}')
    logging.debug(f'In the file {filepath} processed packets: {len(packages)}')
    return packages, is_bin_metadata

# Copy package version from origin to target repository
def backport_version(origin, target, name, add_missing = False):
    if name not in origin:
        logging.error(f'No package in origin: {name}')
        return False
    # Add missing package
    if name not in target:
        target[name] = origin[name]
        logging.info(f'Add package to target: {name}')
        return True
    # Update existing package version
    if (origin[name]['version'] is None or target[name]['version'] != origin[name]['version']) and not add_missing:
        logging.info(f'Replace package in the target, new package: {name}={origin[name]["version"]}')
        target[name] = origin[name]
        return True
    else:
        logging.warning(f'Package version is already in the target: {name}')
    return False

# Resolve binary package name to source package if needed
def resolve_pkg_name(pkg_name, origin, src_dict, prov_dict):
    if pkg_name in origin:
        logging.info(f'Package name remained unchanged: {pkg_name}')
        return pkg_name
    # Check binary-to-source mapping
    elif pkg_name in src_dict:
        logging.info(f'Binary package {pkg_name} resolved to source: {src_dict[pkg_name]}')
        return src_dict[pkg_name]
    # Check provided packages
    elif pkg_name in prov_dict:
        if prov_dict[pkg_name] in src_dict:
            logging.info(f'Binary package {pkg_name} provided by {prov_dict[pkg_name]} resolved to: {src_dict[prov_dict[pkg_name]]}')
            return src_dict[prov_dict[pkg_name]]
        elif prov_dict[pkg_name] in origin:
            logging.info(f'Binary package {pkg_name} provided by: {prov_dict[pkg_name]}')
            return prov_dict[pkg_name]
        else:
            logging.error(f'Resolve binary package: {pkg_name}')
    else:
        logging.warning(f'Package name not found: {pkg_name}')
    return None

# Reverse direction of edges in dependency graph
def reverse_graph(graph):
    reversed_graph = {node: set() for node in graph}
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            reversed_graph[neighbor].add(node)
    return reversed_graph

def dict_to_dot(d, graph_name='G'):
    lines = [f"digraph {graph_name} {{"]
    for key, values in d.items():
        if not isinstance(values, (set, list, tuple)):
            values = [values]
        lines.append(f'    "{key}";')
        for value in values:
            lines.append(f'    "{value}";')
            lines.append(f'    "{key}" -> "{value}";')
    lines.append("}")
    return '\n'.join(lines)

def handle_resolve_src(pkg_name, line_left_side, origin, is_bin_metadata, bin_dict, add_version):
    """Handle --resolve-src operation mode. Returns output string."""
    output = []
    if pkg_name is not None:
        if not is_bin_metadata:
            for p in bin_dict.keys():
                if pkg_name in bin_dict[p]:
                    if add_version:
                        output.append(f'{p}={origin[p]["source_version"]}')
                    else:
                        output.append(p)
        elif pkg_name in origin:
            if add_version:
                output.append(f'{origin[pkg_name]["source"]}={origin[pkg_name]["source_version"]}')
            else:
                output.append(f'{origin[pkg_name]["source"]}')
    return '\n'.join(output)


def handle_resolve_bin(pkg_name, origin, is_bin_metadata, bin_dict, add_version):
    """Handle --resolve-bin operation mode. Returns output string."""
    output = []
    if pkg_name is not None:
        if not is_bin_metadata:
            if pkg_name in bin_dict:
                for p in bin_dict[pkg_name]:
                    output.append(p)
        else:
            for p in origin.keys():
                if origin[p]['source'] == pkg_name:
                    if add_version:
                        output.append(f'{p}={origin[p]["version"]}')
                    else:
                        output.append(p)
    return '\n'.join(output)


def handle_add_version(line_left_side, origin):
    """Handle --add-version operation mode. Returns output string."""
    if line_left_side in origin:
        return f'{line_left_side}={origin[line_left_side]["version"]}'
    else:
        logging.error(f'Package without resolve operation not found: {line_left_side}')
        return ''


def handle_resolve_group(pkg_name, origin, is_bin_metadata, bin_dict, target):
    """Handle --resolve-group operation mode. Returns output string."""
    output = []
    if pkg_name is not None:
        if pkg_name in origin and origin[pkg_name]["source"] is not None:
            if origin[pkg_name]["source"] in bin_dict:
                for p in bin_dict[origin[pkg_name]["source"]]:
                    output.append(p)
            elif not is_bin_metadata:
                for bin_pkgs in bin_dict.values():
                    if pkg_name in bin_pkgs:
                        for p in bin_pkgs:
                            output.append(p)
            else:
                logging.error(f'Can not resolve package binary group for: {pkg_name} via source {target[pkg_name]["source"]}')
    return '\n'.join(output)


def handle_resolve_up(line_left_side, target):
    """Handle --resolve-up operation mode. Returns (dependent_set, output_string)."""
    dependent_set = {}
    output = []
    if line_left_side not in target:
        dependent_found = False
        for key, value in target.items():
            if line_left_side in value['depends']:
                dependent_set[key] = None
                dependent_found = True
                logging.info(f'Resolve the target dependent {key} package for: {line_left_side}')
        if not dependent_found:
            logging.error(f'Can not resolve the target dependent package for: {line_left_side}')
    return dependent_set, '\n'.join(output)


def handle_depends(pkg_name, origin, src_dict, prov_dict, depends_depth, depends_set):
    """Handle --depends operation mode. Returns (depends_set, output_string)."""
    if pkg_name is not None:
        depends_set[pkg_name] = None
        for i in range(depends_depth):
            set_len = len(depends_set)
            for p in dict(depends_set).keys():
                p_src = resolve_pkg_name(p, origin, src_dict, prov_dict)
                if p_src:
                    for pd in origin[p_src].get("depends", []):
                        pd_src = resolve_pkg_name(pd, origin, src_dict, prov_dict)
                        if pd_src:
                            depends_set[pd_src] = None
            if set_len == len(depends_set):
                logging.info(f'Dependency search completed at iteration: {i + 1}')
                break
        else:
            logging.warning(f'Dependency search did not reach all leaf nodes, number of iteration: {depends_depth}')
    output = '\n'.join(depends_set.keys())
    return depends_set, output


def handle_remove(pkg_name, origin):
    """Handle --remove operation mode. Returns empty string (side effects only)."""
    if pkg_name is not None:
        if pkg_name in origin:
            del origin[pkg_name]
            logging.info(f'Package removed: {pkg_name}')
        else:
            logging.error(f'Package to be removed is not present in the target: {pkg_name}')
    return ''


def handle_backport(pkg_name, origin, target, add_missing):
    """Handle default backport operation mode. Returns empty string (side effects only)."""
    if pkg_name is not None:
        backport_version(origin, target, pkg_name, add_missing)
    else:
        logging.error(f'No deletion request and package name is not resolved: {pkg_name}')
    return ''


def handle_topo_sort(packages, target, src_dict, prov_dict, dot_file=None):
    """Handle --topo-sort operation mode. Returns output string."""
    graph = {}
    # Build dependency graph
    for p in packages:
        if p not in graph: graph[p] = set()
        for d in target[p]['depends']:
            pkg_name = resolve_pkg_name(d.split()[0], target, src_dict, prov_dict)
            if pkg_name in packages:
                graph[p].add(pkg_name)
                if pkg_name not in graph: graph[pkg_name] = set()
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


def output_metadata(origin, target, only_one_repo):
    """Output modified package metadata."""
    for pkg in origin.values() if only_one_repo else target.values():
        print(pkg['block'])
        print()


def main():
    # Setup command line argument parser
    parser = argparse.ArgumentParser(description='Pre-dose script performs a targeted substitution of package \
        information from a origin repository to a target repository, only for packages specified in the stdin input list. \
        Note: many options may operate based on binary or sources metadata.')
    parser.add_argument('origin_repo', metavar='ORIGIN_REPO', nargs='?', help='newer repository Packages/Sources')
    parser.add_argument('target_repo', metavar='TARGET_REPO', help='older repository Packages/Sources')
    parser.add_argument('-m', '--add-missing', action='store_true', help='add missing packages do not change versions')
    parser.add_argument('-r', '--remove', action='store_true', help='remove packages instead of replacing or adding')
    parser.add_argument('-p', '--provide', type=str, metavar='PATH', help="path to binary Packages metadata to provide replacements for sources implantation")
    parser.add_argument('-e', '--depends', type=int, metavar='DEPTH', help='print repository package dependencies and exit')
    parser.add_argument('-s', '--resolve-src', action='store_true', help='resolve source code package names and exit')
    parser.add_argument('-b', '--resolve-bin', action='store_true', help='resolve binary package names by original source metadata and exit')
    parser.add_argument('-u', '--resolve-up', action='store_true', help='resolve the target dependent package if the package name is not found in origin and exit')
    parser.add_argument('-o', '--resolve-group', action='store_true', help='resolve target binary group and exit')
    parser.add_argument('-t', '--topo-sort', action='store_true', help='perform topological sort and exit')
    parser.add_argument('-g', '--dot', type=str, help="save toposort graph to dot file")
    parser.add_argument('-a', '--add-version', action='store_true', help='add version to output for resolve operations and exit')
    parser.add_argument('-l', '--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
                       help='set the logging level (default: INFO)')
    parser.add_argument('--log-file', help="save logs to file (default: stderr)")
    args = parser.parse_args()

    # only target args
    only_one_repo = any((args.remove, args.resolve_bin, args.resolve_src, args.resolve_group, args.depends, args.topo_sort))

    # Check args
    if only_one_repo and args.origin_repo is not None:
        parser.error("option does not require ORIGIN_REPO")

    # Configure logging system
    handlers = []
    if args.log_file: handlers.append(logging.FileHandler(args.log_file))
    else: handlers.append(logging.StreamHandler())
    logging.basicConfig(handlers=handlers, level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    logging.info(f'Pre-dose started with command line options: {args}')

    # Initialize data structures
    src_dict = {}
    bin_dict = {}
    group_dict = {}
    prov_dict = {}
    exclude_depends = []
    lines = []
    packages = set()
    # Ordered sets
    depends_set = {}
    dependent_set = {}
    is_bin_metadata = None

    # Parse repository metadata
    origin, is_bin_metadata = parse_metadata(args.origin_repo if not only_one_repo else args.target_repo, \
        src_dict = src_dict, prov_dict = prov_dict, bin_dict = bin_dict)
    if not only_one_repo: target, _ = parse_metadata(args.target_repo, bin_dict = group_dict)
    if args.provide: parse_metadata(args.provide, prov_dict = prov_dict)

    result = None

    # Process input packages from stdin
    for line in sys.stdin:
        if line[0] == "#" or line.strip() == "": continue
        line_left_side = line.strip().split("=")[0] # Package name
        lines.append(line_left_side)
        if any((args.resolve_bin, args.resolve_src)):
            pkg_name = line_left_side
        else:
            pkg_name = resolve_pkg_name(line_left_side, origin, src_dict, prov_dict)
            
        if pkg_name is not None: packages.add(pkg_name)

        # Handle different operation modes via dedicated functions (all return strings)
        if args.resolve_src:
            result = handle_resolve_src(pkg_name, line_left_side, origin, is_bin_metadata, bin_dict, args.add_version)
        elif args.resolve_bin:
            result = handle_resolve_bin(pkg_name, origin, is_bin_metadata, bin_dict, args.add_version)
        elif args.add_version:
            result = handle_add_version(line_left_side, origin)
        elif args.resolve_group:
            result = handle_resolve_group(pkg_name, origin, is_bin_metadata, bin_dict, group_dict)
        elif args.resolve_up:
            dep_set, result = handle_resolve_up(line_left_side, group_dict)
            dependent_set.update(dep_set)
        elif args.depends:
            depends_set, result = handle_depends(pkg_name, origin, src_dict, prov_dict, args.depends, depends_set)
        elif args.topo_sort:
            pass  # Handled after loop
        elif args.remove:
            handle_remove(pkg_name, origin)  # Returns '', no output
        elif pkg_name is not None:
            handle_backport(pkg_name, origin, group_dict if only_one_repo else target, args.add_missing)  # Returns '', no output
        else:
            logging.error(f'No deletion request and package name is not resolved: {line_left_side}')

    # Print collected output for resolve/depends modes
    if result:
        print(result)

    # Perform topological sort if requested (prints directly)
    if args.topo_sort:
        result = handle_topo_sort(packages, target if not only_one_repo else origin, src_dict, prov_dict, args.dot)
        if result:
            print(result)

    # Output modified package metadata if not in special mode
    if not any((args.add_version, args.depends, args.resolve_src, args.resolve_bin,
        args.resolve_group, args.topo_sort, args.resolve_up)):
        output_metadata(origin, target if not only_one_repo else origin, only_one_repo)

    logging.debug(f'Pre-dose finished and the input stream was: {lines}')

if __name__ == "__main__":
    main()