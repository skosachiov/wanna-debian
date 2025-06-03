import re, argparse, sys, logging
from collections import deque

def delete_depends(pkg_name, block, exclude_list):
    result = []
    for line in block.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends'):
                packages = [p.strip() for p in value.split(',')]
                filtered_packages = [p for p in packages if not any((p.startswith(name + " ") or p.startswith(name + ":") or p == name) for name in exclude_list)]
                line = key + ": " + ', '.join(filtered_packages)
                if len(packages) - len(filtered_packages) > 0:
                    logging.debug(f'Removed {len(packages) - len(filtered_packages)} dependencies from package: {pkg_name}')
        result.append(line)
    return "\n".join(result)

def parse_metadata(filepath, src_dict = None, prov_dict = None):
    packages = {}
    with open(filepath, 'rt', encoding='utf-8') as f:
        content = f.read()
        package_blocks = re.split(r'\n\n+', content.strip())
        for block in package_blocks:
            pkg_name = version = None
            depends = []
            for line in block.splitlines():
                if not line or line[0].isspace(): continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    if key == 'Package':
                        pkg_name = value.strip()
                    if key == 'Binary' and src_dict != None:
                        bin_pkgs = [p.strip() for p in value.split(',')]
                        for p in bin_pkgs:
                            src_dict[p] = pkg_name
                    if key == 'Provides' and prov_dict != None:
                        prov_pkgs = [p.strip().split()[0] for p in value.split(',')]
                        for p in prov_pkgs:
                            prov_dict[p] = pkg_name
                    if key == 'Version':
                        version = value.strip()
                    if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends'):
                        deps_pkgs = [p.strip() for p in value.split(',')]
                        for p in deps_pkgs:
                            depends.append(p)
            if pkg_name != None and version != None:
                packages[pkg_name] = {'version': version, 'block': block, 'depends': depends}
    logging.debug(f'In the file {filepath} processed packets: {len(packages)}')
    return packages

def backport_version(origin, target, name):
    if name not in origin:
        logging.error(f'No package in origin: {name}')
        return False
    if name not in target:
        target[name] = origin[name]
        logging.info(f'Add package to target: {name}')
        return True
    if target[name]['version'] != origin[name]['version']:
        logging.info(f'Replace package in the target: {name}')
        target[name] = origin[name]
        return True
    else:
        logging.warning(f'Package version is already in the target: {name}')
    return False

def resolve_pkg_name(pkg_name, origin, src_dict, prov_dict):
    if pkg_name in origin:
        logging.info(f'Package name remained unchanged: {pkg_name}')
        return pkg_name
    elif pkg_name in src_dict:
        logging.info(f'Binary package {pkg_name} resolved to source: {src_dict[pkg_name]}')
        return src_dict[pkg_name]
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

def topological_sort(graph):
    in_degree = {node: 0 for node in graph}
    for node in graph:
        for neighbor in graph[node]:
            in_degree[neighbor] += 1
    queue = deque([node for node in in_degree if in_degree[node] == 0])
    topo_order = []
    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for neighbor in graph[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if len(topo_order) != len(graph):
        logging.error(f'Topological cycle detected: {len(topo_order) - len(graph)}')
        return None
    return topo_order

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pre-dose script performs a targeted substitution of package \
        information from a origin repository to a target repository, only for packages specified in the stdin input list.')
    parser.add_argument('origin_repo', help='newer repository Packages/Sources')
    parser.add_argument('target_repo', help='older repository Packages/Sources')
    parser.add_argument('-r', '--remove', action='store_true', help='remove instead of replacing or adding')
    parser.add_argument('-d', '--delete-depends', action='store_true', help='delete from dependencies instead of replacing or adding')
    parser.add_argument('-p', '--provide', type=str, help="path to binary Packages to provide replacements for sources implantation")
    parser.add_argument('-e', '--depends', action='store_true', help='print repository package dependencies and exit')        
    parser.add_argument('-s', '--resolve', action='store_true', help='resolve package names and exit')
    parser.add_argument('-t', '--topo-sort', action='store_true', help='perform topological sort on origin and exit')    
    parser.add_argument('-a', '--add-version', action='store_true', help='add version to package name and exit')
    parser.add_argument('-l', '--log-level', default='DEBUG', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
                       help='set the logging level (default: DEBUG)')    
    parser.add_argument('--log-file', help="save logs to file (default: stderr)")
    args = parser.parse_args()

    handlers = []
    if args.log_file: handlers.append(logging.FileHandler(args.log_file)) 
    else: handlers.append(logging.StreamHandler())
    logging.basicConfig(handlers=handlers, level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    logging.debug(f'Pre-dose started with command line options: {args}')

    src_dict = {}
    prov_dict = {}
    exclude_depends = []
    lines = []
    packages = set()

    origin = parse_metadata(args.origin_repo, src_dict = src_dict, prov_dict = prov_dict)
    target = parse_metadata(args.target_repo)
    if args.provide: parse_metadata(args.provide, prov_dict = prov_dict)

    for line in sys.stdin:
        if line[0] == "#" or line.strip() == "": continue
        lines.append(line.strip())        
        pkg_name = resolve_pkg_name(line.strip(), origin, src_dict, prov_dict)
        if pkg_name != None: packages.add(pkg_name)
        if args.add_version and not args.resolve and pkg_name != None:
            print(f'{line.strip()}={origin[line.strip()]["version"]}')
        elif args.resolve and pkg_name != None:
            if args.add_version:
                print(f'{pkg_name}={origin[pkg_name]["version"]}')
            else:
                print(f'{pkg_name}')
        elif args.depends and pkg_name != None:
            for p in origin[pkg_name]["depends"]:
                print(p)
        elif args.delete_depends:
            exclude_depends.append(line.strip())
        elif args.remove and pkg_name != None:
            if pkg_name in target:
                del target[pkg_name]
                logging.info(f'Package removed: {pkg_name}')
            else:
                logging.error(f'Package to be removed is not present in the target: {pkg_name}')
        elif pkg_name != None:
            backport_version(origin, target, pkg_name)
        else:
            logging.error(f'No deletion request and package name is not resolved: {line.strip()}')

    if args.delete_depends:
        for k, v in target.items():
            v['block'] = delete_depends(k, v['block'], exclude_depends)
    
    if args.topo_sort:
        graph = {}
        for p in packages:
            if p not in graph: graph[p] = set()
            for d in origin[p]['depends']:
                pkg_name = resolve_pkg_name(d, origin, src_dict, prov_dict)
                if pkg_name != None:
                    graph[p].add(pkg_name)
                    if pkg_name not in graph: graph[pkg_name] = set()
        for p in topological_sort(graph):
            print(p)

    if not any((args.add_version, args.depends, args.resolve, args.topo_sort)):
        for pkg in target.values():
            print(pkg['block'])
            print()

    logging.debug(f'Pre-dose finished and the input stream was: {lines}')
    