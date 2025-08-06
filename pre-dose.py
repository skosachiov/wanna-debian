import re, argparse, sys, logging
from toposort import *

import apt_pkg
apt_pkg.init_system()

# Remove specified dependencies from a package's metadata block
def delete_depends(pkg_name, block, exclude_list):
    result = []
    for line in block.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            # Process dependency fields
            if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends'):
                packages = [p.strip() for p in value.split(',')]
                # Filter out excluded packages
                filtered_packages = [p for p in packages if not any((p.startswith(name + " ") or p.startswith(name + ":") or p == name) for name in exclude_list)]
                line = key + ": " + ', '.join(filtered_packages)
                if len(packages) - len(filtered_packages) > 0:
                    logging.debug(f'Removed {len(packages) - len(filtered_packages)} dependencies from package: {pkg_name}')
        result.append(line)
    return "\n".join(result)

# Parse package metadata from repository file
def parse_metadata(filepath, src_dict = None, prov_dict = None, bin_dict = None):
    packages = {}
    with open(filepath, 'rt', encoding='utf-8') as f:
        content = f.read()
        # Split into individual package blocks
        package_blocks = re.split(r'\n\n+', content.strip())
        for block in package_blocks:
            pkg_name = version = source = None
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
                        pkg_name = value.strip()
                    # Build binary-to-source mapping for source metadata if requested
                    if key == 'Binary' and src_dict != None:
                        bin_pkgs = [p.strip() for p in value.split(',')]
                        if bin_dict != None: bin_dict[pkg_name] = bin_pkgs
                        for p in bin_pkgs:
                            src_dict[p] = pkg_name
                    # Build binary-to-source mapping for binary metadata if requested
                    if key == 'Source' and bin_dict != None:
                        source = value.strip().split()[0]
                        if source not in bin_dict:
                            bin_dict[source] = [pkg_name]
                        else:
                            bin_dict[source].append(pkg_name)
                    # Build provides mapping if requested
                    if key == 'Provides' and prov_dict != None:
                        # prov_pkgs = [p.strip().split()[0] for p in value.split(',') if "default-dev" not in p and "divert-dev" not in p]
                        prov_pkgs = [p.strip().split()[0] for p in value.split(',')]
                        for p in prov_pkgs:
                            prov_dict[p] = pkg_name
                    # Extract version
                    if key == 'Version':
                        version = value.strip()
                    # Collect dependencies
                    if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends', 'Pre-Depends'):
                        deps_pkgs = [p.strip().split()[0].split(":")[0] for p in value.split(',') if p.strip() and '<!' not in p]
                        for p in deps_pkgs:
                            if p == pkg_name:
                                logging.warning(f'package depends on itself, '
                                    f'package name is excluded from dependencies: {pkg_name}')
                                continue       
                            depends.append(p)
            # Store package metadata if valid
            if pkg_name != None and version != None:
                if pkg_name not in packages or apt_pkg.version_compare(version, packages[pkg_name]['version']) > 0:
                    packages[pkg_name] = {'version': version, 'block': block, 'depends': depends, 'source': source}
                else:
                    logging.warning(f'A new version package already in the list: {pkg_name}')                
    logging.debug(f'In the file {filepath} processed packets: {len(packages)}')
    return packages

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
    if target[name]['version'] != origin[name]['version'] and not add_missing:
        logging.info(f'Replace package in the target: {name}')
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

if __name__ == "__main__":
    # Setup command line argument parser
    parser = argparse.ArgumentParser(description='Pre-dose script performs a targeted substitution of package \
        information from a origin repository to a target repository, only for packages specified in the stdin input list.')
    parser.add_argument('origin_repo', help='newer repository Packages/Sources')
    parser.add_argument('target_repo', help='older repository Packages/Sources')
    parser.add_argument('-m', '--add-missing', action='store_true', help='add missing packages do not change versions')
    parser.add_argument('-r', '--remove', action='store_true', help='remove packages instead of replacing or adding')
    parser.add_argument('-d', '--delete-depends', action='store_true', help='delete from dependencies instead of replacing or adding')
    parser.add_argument('-p', '--provide', type=str, metavar='PATH', help="path to binary Packages metadata to provide replacements for sources implantation")
    parser.add_argument('-e', '--depends', type=int, metavar='DEPTH', help='print repository package dependencies and exit')        
    parser.add_argument('-s', '--resolve-src', action='store_true', help='resolve source code package names and exit')
    parser.add_argument('-b', '--resolve-bin', action='store_true', help='resolve binary package names by original source metadata and exit')
    parser.add_argument('-o', '--resolve-group', action='store_true', help='resolve target binary group and exit')
    parser.add_argument('-t', '--topo-sort', action='store_true', help='perform topological sort on origin and exit')   
    parser.add_argument('-g', '--dot', type=str, help="save toposort graph to dot file")
    parser.add_argument('-a', '--add-version', action='store_true', help='add version to package name and exit')
    parser.add_argument('-l', '--log-level', default='DEBUG', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
                       help='set the logging level (default: DEBUG)')    
    parser.add_argument('--log-file', help="save logs to file (default: stderr)")
    args = parser.parse_args()

    # Configure logging system
    handlers = []
    if args.log_file: handlers.append(logging.FileHandler(args.log_file)) 
    else: handlers.append(logging.StreamHandler())
    logging.basicConfig(handlers=handlers, level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    logging.debug(f'Pre-dose started with command line options: {args}')

    # Initialize data structures
    src_dict = {}
    bin_dict = {}
    group_dict = {}
    prov_dict = {}
    exclude_depends = []
    lines = []
    packages = set()
    depends_set = {} # Ordered dict

    # Parse repository metadata
    origin = parse_metadata(args.origin_repo, src_dict = src_dict, prov_dict = prov_dict, bin_dict = bin_dict if args.resolve_bin != None else None)
    target = parse_metadata(args.target_repo, bin_dict = group_dict)
    if args.provide: parse_metadata(args.provide, prov_dict = prov_dict)

    # Process input packages from stdin
    for line in sys.stdin:
        if line[0] == "#" or line.strip() == "": continue
        line_left_side = line.strip().split("=")[0] # Package name
        lines.append(line_left_side)
        pkg_name = resolve_pkg_name(line_left_side, origin, src_dict, prov_dict)
        if pkg_name != None: packages.add(pkg_name)
        
        # Handle different operation modes
        if args.add_version and not (args.resolve_src or args.resolve_bin or args.resolve_group) and pkg_name != None:
            if line_left_side in origin:
                print(f'{line_left_side}={origin[line_left_side]["version"]}')
            else:
                logging.error(f'Package without resolve operation not found: {line_left_side}')
        elif args.resolve_src and pkg_name != None:
            if args.add_version:
                print(f'{pkg_name}={origin[pkg_name]["version"]}')
            else:
                print(f'{pkg_name}')
        elif args.resolve_bin and pkg_name != None:
            if pkg_name in bin_dict:
                for p in bin_dict[pkg_name]:
                    print(p)
            else:
                logging.error(f'Can not resolve the source package to binary because the name was not found: {pkg_name}')
        elif args.resolve_group and pkg_name != None:
            if pkg_name in target and target[pkg_name]["source"] != None:  
                for p in group_dict[target[pkg_name]["source"]]:
                    print(p)                
        elif args.depends and pkg_name != None:
            depends_set[pkg_name] = None # Set
            for i in range(args.depends):
                set_len = len(depends_set)
                for p in dict(depends_set).keys():
                    p_src = resolve_pkg_name(p, origin, src_dict, prov_dict)
                    if p_src:
                        for pd in origin[p_src]["depends"]:
                            pd_src = resolve_pkg_name(pd, origin, src_dict, prov_dict)
                            if pd_src:
                                depends_set[pd_src] = None
                if set_len == len(depends_set):
                    logging.info(f'Dependency search completed at iteration: {i + 1}')
                    break
            else:
                logging.warning(f'Dependency search did not reach all leaf nodes, number of iteration: {args.depends}')
        elif args.topo_sort:
            pass
        elif args.delete_depends:
            exclude_depends.append(line_left_side)
        elif args.remove and pkg_name != None:
            if pkg_name in target:
                del target[pkg_name]
                logging.info(f'Package removed: {pkg_name}')
            else:
                logging.error(f'Package to be removed is not present in the target: {pkg_name}')
        elif pkg_name != None:
            backport_version(origin, target, pkg_name, args.add_missing)
        else:
            logging.error(f'No deletion request and package name is not resolved: {line_left_side}')

    # Process dependency deletion if requested
    if args.delete_depends:
        for k, v in target.items():
            v['block'] = delete_depends(k, v['block'], exclude_depends)

    # Process dependency resolve requested
    for p in depends_set.keys():
        print(p)

    # Perform topological sort if requested
    if args.topo_sort:
        graph = {}
        # Build dependency graph
        for p in packages:
            if p not in graph: graph[p] = set()
            for d in origin[p]['depends']:
                pkg_name = resolve_pkg_name(d.split()[0], origin, src_dict, prov_dict)
                if pkg_name in packages:
                    graph[p].add(pkg_name)
                    if pkg_name not in graph: graph[pkg_name] = set()
        # Save graph to dot file
        if args.dot: 
            with open(args.dot, 'w') as f:
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
        for t in sorted(tl):
            print(t)

    # Output modified package metadata if not in special mode
    if not any((args.add_version, args.depends, args.resolve_src, args.resolve_bin, args.resolve_group, args.topo_sort)):
        for pkg in target.values():
            print(pkg['block'])
            print()

    logging.debug(f'Pre-dose finished and the input stream was: {lines}')
    