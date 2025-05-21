import re, argparse, sys

def delete_depends(block, exclude_list):
    result = []
    for line in block.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            if key == 'Build-Depends':
                packages = [p.strip() for p in value.split(',')]
                filtered_packages = [p for p in packages if not any((p.startswith(name + " ") or p == name) for name in exclude_list)]
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
            if pkg_name != None and version != None:
                packages[pkg_name] = {'version': version, 'block': block}
    return packages

def backport_version(source, target, name):
    if name not in source:
        print(f'Error: no name {name} in source', file=sys.stderr)
        return False
    if name not in target:
        target[name] = source[name]
        return True
    if target[name]['version'] != source[name]['version']:
        target[name] = source[name]
        return True
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pre-dose script performs a targeted substitution of package \
        information from a source repository to a target repository, only for packages specified in the stdin input list.')
    parser.add_argument('source_repo', help='Newer repo Sources')
    parser.add_argument('target_repo', help='Older repo Sources')
    parser.add_argument('-r', '--remove', action='store_true', help='remove instead of replacing or adding')
    parser.add_argument('-d', '--delete-depends', action='store_true', help='delete from build depends instead of replacing or adding')
    parser.add_argument('-n', '--dont-resolve', action='store_true', help='do not try to resolve the package name in the source repo')
    parser.add_argument('-a', '--add-version', action='store_true', help='add source version to package name')
    parser.add_argument('-p', '--provide', type=str, help="path to binary Packages to provide replacement")
    args = parser.parse_args()

    src_dict = {}
    prov_dict = {}

    source = parse_local_packages(args.source_repo, src_dict = src_dict)
    target = parse_local_packages(args.target_repo)
    if args.provide: parse_local_packages(args.provide, prov_dict = prov_dict)

    if args.delete_depends:
        exclude_depends = []
        for line in sys.stdin:
            if line[0] == "#": continue
            exclude_depends.append(line.strip())
        for v in target.values():
            v['block'] = delete_depends(v['block'], exclude_depends)
    else:
        for line in sys.stdin:
            if line[0] == "#": continue
            pkg_name = line.strip()
            if args.add_version:
                if pkg_name in source:
                    print(f'{pkg_name}={source[pkg_name]["version"]}', file=sys.stderr)
            if args.remove:
                if pkg_name in target:
                    del target[pkg_name]
                    print(f'Package removed: {pkg_name}', file=sys.stderr)
                else:
                    print(f'Remove package error: {pkg_name}', file=sys.stderr)
            else:
                if pkg_name in source:
                    if backport_version(source, target, pkg_name):
                        print(f'Name has not been changed: {pkg_name}', file=sys.stderr)
                else:
                    if not args.dont_resolve:
                        if pkg_name in src_dict:
                            if backport_version(source, target, src_dict[pkg_name]):
                                print(f'Source name {pkg_name} resolved: {src_dict[pkg_name]}', file=sys.stderr)
                        elif pkg_name in prov_dict:
                            if backport_version(source, target, src_dict[prov_dict[pkg_name]]):
                                print(f'Source name {pkg_name} provided by {prov_dict[pkg_name]}: {src_dict[prov_dict[pkg_name]]}', file=sys.stderr)
                        else:
                            print(f'Resolve binary error: {pkg_name}', file=sys.stderr)
                    else:
                        print(f'Package name error: {pkg_name}', file=sys.stderr)
    
    for pkg in target.values():
        print(pkg['block'])
        print()
    print(prov_dict)
