import re, argparse, sys

def reversed_deps(block):
    result = []
    for line in block.splitlines():
        if ':' in line: key, value = line.split(':', 1)
        if key == 'Build-Depends':
            elements = [x.strip() for x in value.split(',')]
            line = key + ": " + ', '.join(list(reversed(elements)))
        result.append(line)
    return "\n".join(result)

def parse_local_packages(filepath, change_order = False):
    packages = {}
    with open(filepath, 'rt', encoding='utf-8') as f:
        content = f.read()
        package_blocks = re.split(r'\n\n+', content.strip())
        for block in package_blocks:
            for line in block.splitlines():
                if line[0].isspace(): continue
                else:
                    if ':' in line: key, value = line.split(':', 1)
                if key == 'Package':
                    packages[value.strip()] = reversed_deps(block) if change_order else block
                    break
    return packages

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pre-dose script performs a targeted substitution of package information from a source repository to a target repository, only for packages specified in the stdin input list.')
    parser.add_argument('source_repo', help='Newer repo Packages/Sources')
    parser.add_argument('target_repo', help='Older repo Packages/Sources')
    parser.add_argument('-o', '--change-order', action='store_true', help='reversed build dependency list')
    parser.add_argument('-r', '--remove', action='store_true', help='remove instead of replacing or adding')
    args = parser.parse_args()

    source = parse_local_packages(args.source_repo, args.change_order)
    target = parse_local_packages(args.target_repo)

    for line in sys.stdin:
        if line[0] == "#": continue
        pkg_name = line.strip()
        if args.remove:
            if pkg_name in target:
                del target[pkg_name]
        else:
            if pkg_name in source:
                target[pkg_name] = source[pkg_name]
            else:
                print("Package name error:", line.strip(), file=sys.stderr)
    
    for pkg in target.values():
        print(pkg)
        print()
