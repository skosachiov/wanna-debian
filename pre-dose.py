import re, argparse, sys, logging

def delete_depends(block, exclude_list):
    result = []
    for line in block.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends'):
                packages = [p.strip() for p in value.split(',')]
                filtered_packages = [p for p in packages if not any((p.startswith(name + " ") or p.startswith(name + ":") or p == name) for name in exclude_list)]
                line = key + ": " + ', '.join(filtered_packages)
                if len(packages) - len(filtered_packages) > 0:
                    logging.debug(f'Dependencies were removed: {len(packages) - len(filtered_packages)}')
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pre-dose script performs a targeted substitution of package \
        information from a origin repository to a target repository, only for packages specified in the stdin input list.')
    parser.add_argument('origin_repo', help='newer repository Packages/Sources')
    parser.add_argument('target_repo', help='older repository Packages/Sources')
    parser.add_argument('-r', '--remove', action='store_true', help='remove instead of replacing or adding')
    parser.add_argument('-d', '--delete-depends', action='store_true', help='delete from dependencies instead of replacing or adding')
    parser.add_argument('-p', '--provide', type=str, help="path to binary Packages to provide replacements for sources implantation")
    parser.add_argument('-e', '--depends', action='store_true', help='print repository package dependencies and exit')        
    parser.add_argument('-s', '--resolve', action='store_true', help='resolve package name and exit')    
    parser.add_argument('-a', '--add-version', action='store_true', help='add version to package name and exit')
    parser.add_argument('-l', '--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
                       help='set the logging level (default: INFO)')    
    parser.add_argument('--log-file', help="save logs to file (default: stderr)")
    args = parser.parse_args()

    handlers = []
    if args.log_file: handlers.append(logging.FileHandler(args.log_file)) 
    else: handlers.append(logging.StreamHandler())
    logging.basicConfig(handlers=handlers, level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    src_dict = {}
    prov_dict = {}
    exclude_depends = []

    origin = parse_metadata(args.origin_repo, src_dict = src_dict, prov_dict = prov_dict)
    target = parse_metadata(args.target_repo)
    if args.provide: parse_metadata(args.provide, prov_dict = prov_dict)

    for line in sys.stdin:
        if line[0] == "#": continue
        if line.strip() == "": continue
        pkg_name = resolve_pkg_name(line.strip(), origin, src_dict, prov_dict)
        if pkg_name == None: continue
        if args.add_version and not args.resolve:
            print(f'{line.strip()}={origin[line.strip()]["version"]}')
        elif args.resolve:
            if args.add_version:
                print(f'{pkg_name}={origin[pkg_name]["version"]}')
            else:
                print(f'{pkg_name}')
        elif args.depends:
            for p in origin[pkg_name]["depends"]:
                print(p)
        elif args.delete_depends:
            exclude_depends.append(line.strip())
        elif args.remove:
            if pkg_name in target:
                del target[pkg_name]
                logging.info(f'Package removed: {pkg_name}')
            else:
                logging.error(f'Package to be removed is not present in the target: {pkg_name}')
        else:
            backport_version(origin, target, pkg_name)

    if args.delete_depends:
        for v in target.values():
            v['block'] = delete_depends(v['block'], exclude_depends)

    if not any((args.add_version, args.depends, args.resolve)):
        for pkg in target.values():
            print(pkg['block'])
            print()
    