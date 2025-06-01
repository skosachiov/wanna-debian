import re, argparse, sys

def delete_depends(block, exclude_list):
    result = []
    for line in block.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends'):
                packages = [p.strip() for p in value.split(',')]
                filtered_packages = [p for p in packages if not any((p.startswith(name + " ") or p.startswith(name + ":") or p == name) for name in exclude_list)]
                line = key + ": " + ', '.join(filtered_packages)
        result.append(line)
    return "\n".join(result)

def parse_local_packages(filepath, src_dict = None, prov_dict = None):
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
    return packages

def backport_version(origin, target, name):
    if name not in origin:
        print(f'Error: no name {name} in origin', file=sys.stderr)
        return False
    if name not in target:
        target[name] = origin[name]
        return True
    if target[name]['version'] != origin[name]['version']:
        target[name] = origin[name]
        return True
    return False

def resolve_pkg_name(pkg_name, origin, src_dict, prov_dict):
    if pkg_name in origin:
        print(f'Name has not been changed: {pkg_name}', file=sys.stderr)
        return pkg_name
    elif pkg_name in src_dict:
        print(f'Binary package {pkg_name} resolved to source: {src_dict[pkg_name]}', file=sys.stderr)
        return src_dict[pkg_name]
    elif pkg_name in prov_dict:
        if prov_dict[pkg_name] in src_dict:
            print(f'Binary package {pkg_name} provided by {prov_dict[pkg_name]} resolved to: {src_dict[prov_dict[pkg_name]]}', file=sys.stderr)
            return src_dict[prov_dict[pkg_name]]
        elif prov_dict[pkg_name] in origin:
            print(f'Binary package {pkg_name} provided by: {prov_dict[pkg_name]}', file=sys.stderr)
            return prov_dict[pkg_name]
        else:
            print(f'Resolve binary package error: {pkg_name}', file=sys.stderr)
    else:
        print(f'Package name error: {pkg_name}', file=sys.stderr)
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
    args = parser.parse_args()

    src_dict = {}
    prov_dict = {}
    exclude_depends = []

    origin = parse_local_packages(args.origin_repo, src_dict = src_dict, prov_dict = prov_dict)
    target = parse_local_packages(args.target_repo)
    if args.provide: parse_local_packages(args.provide, prov_dict = prov_dict)

    for line in sys.stdin:
        if line[0] == "#": continue
        pkg_name = resolve_pkg_name(line.strip(), origin, src_dict, prov_dict)
        if pkg_name == None: continue
        if args.add_version:
            print(f'{pkg_name}={origin[pkg_name]["version"]}')
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
                print(f'Package removed: {pkg_name}', file=sys.stderr)
            else:
                print(f'Remove package error: {pkg_name}', file=sys.stderr)
        else:
            backport_version(origin, target, pkg_name)

    if args.delete_depends:
        for v in target.values():
            v['block'] = delete_depends(v['block'], exclude_depends)

    if not any((args.add_version, args.depends, args.resolve)):
        for pkg in target.values():
            print(pkg['block'])
            print()
    