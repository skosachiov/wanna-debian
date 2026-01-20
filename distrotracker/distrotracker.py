#!/usr/bin/env python3

import os, gzip, lzma, shutil, requests
import time, argparse, logging, json, hashlib, re, apt_pkg, sys
from urllib.parse import urljoin, urlparse
from datetime import datetime
from functools import cmp_to_key


def write_metadata_index(filename, data_list):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('[\n')  # Start with list bracket
            items = []
            for item in data_list:
                # Convert each item to JSON string without indentation
                item_str = json.dumps(item, separators=(',', ':'))
                items.append(f'  {item_str}')
            f.write(',\n'.join(items))
            f.write('\n]')  # End with list bracket
        logging.info(f"List successfully written to: {filename}")
    except IOError as e:
        logging.error(f"Error writing to file: {e}")

def update_metadata_index(packagefile, data_list, dist, comp, build):
    packages = data_list
    with open(packagefile, 'rt', encoding='utf-8') as f:
        content = f.read()
        # Split into individual package blocks
        package_blocks = re.split(r'\n\n+', content.strip())
        for block in package_blocks:
            pkg_name = version = arch = filename = directory = source = source_version = None
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
                    # Build binary-to-source mapping for binary metadata if requested
                    if key == 'Source':
                        source_line = value.strip().split()
                        if len(source_line) > 0:
                            source = source_line[0]
                            if len(source_line) > 1: source_version = re.findall(r'\((.*?)\)', source_line[1])[0]
                   # Extract version
                    if key == 'Version':
                        version = value.strip()
                   # Extract architecture
                    if key == 'Architecture':
                        arch = value.strip()
                   # Extract filename
                    if key == 'Filename':
                        filename = value.strip()
                   # Extract directory
                    if key == 'Directory':
                        directory = value.strip()
                    # Collect dependencies
                    if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends', 'Pre-Depends'):
                        depends.append(value)
            # Store package metadata if valid
            if pkg_name is not None:
                if source is None: source = pkg_name
                if source_version is None: source_version = version
                packages.append({ \
                    'package': pkg_name, 'version': version, 'dist': dist, 'comp': comp, 'build': build, 'arch': arch, \
                    'depends': hashlib.md5(",".join(depends).encode()).hexdigest()[:8], \
                    'source': source, 'source_version': source_version, \
                    'filename': filename if filename else directory + "/" + pkg_name + "_" + version.split(":")[-1] + ".dsc" })
    logging.debug(f'In the file {packagefile} processed packets: {len(packages)}')
    return packages

def parse_requirement_line(line):

    # Handle lines with trailing comments or other characters
    line = line.split('#')[0].strip()  # Remove comments
    if not line:
        return None

    # Use regex for more robust parsing
    pattern = r'^([a-zA-Z0-9\-\._\+]+)\s*\(\s*([=><]+)\s*([^\)]+)\s*\)$'
    match = re.match(pattern, line)

    if match:
        package_part = match.group(1).strip()
        operator = match.group(2).strip()
        version = match.group(3).strip()
        if operator in ('>=', '<=', '>>', '<<', '='):
            return (package_part, operator, version)
    else:
        package_part = line
        operator = '>='
        version = '0~~'
        return (package_part, operator, version)

    return None

def check_version(version, required_op, required_version):
    """
    Check if installed version satisfies the Debian requirement
    """
    comparison = apt_pkg.version_compare(version, required_version)

    if required_op == '=':
        return comparison == 0
    elif required_op == '>=':
        return comparison >= 0
    elif required_op == '<=':
        return comparison <= 0
    elif required_op == '>>':
        return comparison > 0
    elif required_op == '<<':
        return comparison < 0
    else:
        return False

def find_versions(fin, filename, dist = None, build = None, briefly = None, index_key = 'package', selection = None):

    version_key = "source_version" if index_key == "source" else "version"

    if not os.path.exists(filename):
        logging.error(f"File does not exist: {filename}")
        return {}
    data_dict = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
        for e in data_list:
            if build and e['build'] not in build: continue
            if dist and e['dist'] not in dist: continue
            if e[index_key] not in data_dict:
                data_dict[e[index_key]] = [e]
            else:
                data_dict[e[index_key]].append(e)
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error reading file: {e}")
        return {}
    logging.info(f"Dictionary successfully read from: {filename}")
    for key in data_dict:
        data_dict[key].sort(key=cmp_to_key(lambda a, b: apt_pkg.version_compare(a[version_key], b[version_key])))

    briefly_keys = ['package', 'version', 'dist', 'build', 'source']
    items = []
    for line in fin:
        req = parse_requirement_line(line)
        if not req:
            continue
        package_name, operator, required_version = req

        if package_name not in data_dict:
            logging.warning(f"Can not find package name: {package_name} ({operator} {required_version})")
            continue

        package_prev = None
        p_items = []
        for p in data_dict[package_name]:
            if check_version(p[version_key], operator, required_version):
                item_str = json.dumps({k: v for k, v in p.items() if k in briefly_keys} if briefly else p)
                p_items.append(f'  {item_str}')
                package_prev = p[index_key]
        if not package_prev:
            logging.warning(f"Package versions found do not meet the conditions: {package_name} ({operator} {required_version})")

        if selection == "latest": p_items = p_items[-1:]
        if selection == "earliest": p_items = p_items[:0]
        items.expand(p_items)

    print("[")
    print(',\n'.join(items))
    print("]")

def original_metadata_is_newer(base_url, local_base_dir, session):
    """
    Check if specific Debian metadata files are newer than local ones and update if needed.
    Builds local paths from URL structure.
    Returns True if remote updated, False if no update needed.
    """
    # Specific metadata files to check
    metadata_dirs = [
        # 'db/references.db',
        'ls-lR.gz',
        'db/release.caches.db',
        'indices/files/arch-amd64.files',
        'indices/files/components/source.list.gz'
    ]

    # Base local directory
    os.makedirs(local_base_dir, exist_ok=True)

    updated = True

    for metadata_dir in metadata_dirs:
        url = base_url + metadata_dir
        try:
            # Build local path from URL
            parsed_url = urlparse(url)
            # Remove leading slash and split path
            url_path = parsed_url.path.lstrip('/')
            local_path = os.path.join(local_base_dir, url_path)

            # Create directory structure if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Check if file exists locally
            if os.path.exists(local_path):
                local_mtime = os.path.getmtime(local_path)

                # Get remote file headers to check last-modified
                head_response = session.head(url)
                head_response.raise_for_status()

                if 'last-modified' in head_response.headers:
                    remote_time_str = head_response.headers['last-modified']
                    remote_time = datetime.strptime(remote_time_str, '%a, %d %b %Y %H:%M:%S %Z').timestamp()

                    if remote_time > local_mtime:
                        logging.info(f"Updating (remote is newer): {url_path}")
                        # Download the updated file
                        file_response = session.get(url)
                        file_response.raise_for_status()

                        with open(local_path, 'wb') as f:
                            f.write(file_response.content)

                        # Update local modification time to match remote
                        os.utime(local_path, (remote_time, remote_time))

                        extract_compressed_file(local_path, local_path[:-3], remote_time)

                    else:
                        logging.info(f"Url is up to date: {url_path}")
                        updated = False
                else:
                    logging.warning(f"No last-modified header for: {url}")
            else:
                # File doesn't exist locally, download it
                logging.info(f"Downloading new file: {url_path}")
                file_response = session.get(url)
                file_response.raise_for_status()

                with open(local_path, 'wb') as f:
                    f.write(file_response.content)

                # Set modification time from server if available
                if 'last-modified' in file_response.headers:
                    remote_time_str = file_response.headers['last-modified']
                    remote_time = datetime.strptime(remote_time_str, '%a, %d %b %Y %H:%M:%S %Z').timestamp()
                    os.utime(local_path, (remote_time, remote_time))

                extract_compressed_file(local_path, local_path[:-3], remote_time)

        except requests.RequestException as e:
            logging.warning(f"No processing {url}: {e}")
            continue

    return updated

def get_distributions(base_url, session):
    """Get list of distributions from the Debian repository"""
    try:
        response = session.get(base_url)
        response.raise_for_status()

        # Parse distributions from the directory listing
        distributions = []
        for line in response.text.split('\n'):
            if 'href="' in line and 'Parent Directory' not in line:
                # Extract distribution name from href
                start = line.find('href="') + 6
                end = line.find('"', start)
                dist = line[start:end].rstrip('/')
                if dist and not dist.startswith(('.', '?')):
                    distributions.append(dist)

        return distributions

    except requests.RequestException as e:
        logging.error(f"Error fetching distributions: {e}")
        return []

def should_download_file(local_path, remote_last_modified):
    """Check if local file is older than remote file or doesn't exist"""
    if not os.path.exists(local_path):
        return True

    local_mtime = os.path.getmtime(local_path)
    local_time = datetime.fromtimestamp(local_mtime)

    # Parse remote last-modified date
    remote_time = datetime.strptime(remote_last_modified, '%a, %d %b %Y %H:%M:%S %Z')

    return local_time < remote_time

def download_file(url, local_path, session):
    """Download a file if local version is older or doesn't exist"""
    logging.info(f"Trying to download: {url}")
    try:
        # Get file info first to check last-modified
        head_response = session.head(url)
        head_response.raise_for_status()

        last_modified = head_response.headers.get('last-modified')
        if not last_modified:
            logging.warning(f"No last-modified header for {url}, forcing download")
            last_modified = "Thu, 01 Jan 1970 00:00:00 GMT"  # Force download

        if should_download_file(local_path, last_modified):
            logging.info(f"Downloading: {url}")
            response = session.get(url)
            response.raise_for_status()

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Save the file
            with open(local_path, 'wb') as f:
                f.write(response.content)

            # Set file modification time to match remote
            remote_time = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S %Z')
            timestamp = time.mktime(remote_time.timetuple())
            os.utime(local_path, (timestamp, timestamp))

            return True
        else:
            logging.info(f"Skipping (up to date): {os.path.basename(local_path)}")
            return False

    except requests.RequestException as e:
        logging.debug(f"Can not download: {e}")
        return None

def extract_compressed_file(compressed_path, extract_path, remote_time=None):
    # Extract compressed file if supported
    extension_handlers = {'.gz': gzip.open, '.xz': lzma.open}

    for ext, open_func in extension_handlers.items():
        if compressed_path.endswith(ext):
            try:
                with open_func(compressed_path, 'rb') as f_in:
                    with open(extract_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                # Set same modification time for extracted file
                if remote_time is not None:  # Fixed: "is not" instead of "in not"
                    os.utime(extract_path, (remote_time, remote_time))
                logging.info(f"Extracted to: {extract_path}")
                return True
            except Exception as e:
                logging.error(f"Error extracting {compressed_path}: {e}")
                return False

    # If no supported extension found
    logging.error(f"Unsupported file extension: {compressed_path}")
    return False

def update_metadata(base_url, local_base_dir, dists, components, builds, session):
    """Main function to update Debian repository metadata"""

    try:
        os.remove(local_base_dir + "/status")
    except Exception as e:
        pass

    logging.info("Fetching distributions list...")
    distributions = get_distributions(base_url + "/dists/", session)

    if not distributions:
        logging.error("No distributions found!")
        return

    logging.info(f"Found {len(distributions)} distributions: {', '.join(distributions)}")

    # Files to download for each distribution
    data_list = []
    metadata_files = []
    for build in builds:
        if build == "source":
            metadata_files.append(build + "/Sources")
        else:
            metadata_files.append(build + "/Packages")

    for dist in distributions:
        if dists and dist not in dists:
            continue
        logging.info(f"Processing distribution: {dist}")
        dist_url = urljoin(base_url, "dists/" + dist + "/")
        dist_dir = os.path.join(local_base_dir, "dists/" + dist)

        for component in components:
            for metadata_file in metadata_files:
                download_status = None
                for extension in ['.gz', '.xz']:
                    file_path = component + "/" + metadata_file + extension
                    remote_url = urljoin(dist_url, file_path)
                    local_z_path = os.path.join(dist_dir, file_path)
                    download_status = download_file(remote_url, local_z_path, session)
                    if download_status is not None:
                        break

                # Process result
                output_filename = os.path.basename(file_path).replace('.gz', '').replace('.xz', '')
                output_dir = os.path.dirname(local_z_path)
                output_path = os.path.join(output_dir, output_filename)

                if download_status:
                    extract_compressed_file(local_z_path, output_path)

                if download_status is not None:
                    update_metadata_index(output_path, data_list, dist, component, metadata_file.split("/")[0])
                else:
                    logging.warning(f"Can not download: {urljoin(dist_url, file_path)[:-2]}[gz|xz])")

                file_path = component + "/" + metadata_file
                # Download file
                remote_url = urljoin(dist_url, file_path)
                local_z_path = os.path.join(dist_dir, file_path)

    write_metadata_index(local_base_dir + "/index.json", data_list)

    with open(local_base_dir + "/status", "w") as f:
        json.dump({'base_url': base_url, 'comp': components, 'timestamp': str(time.time())}, f)

def main():
    """Main entry point"""

    parser = argparse.ArgumentParser(description="Update Debian metadata files from the Debian repository")
    parser.add_argument("--base-url", help="Base URL for Debian metadata (example: https://ftp.debian.org/debian/)")
    parser.add_argument("--local-dir", default="./metadata", help="Local directory to store metadata files (default: %(default)s)")
    parser.add_argument("--dist", default=[], nargs='+', help="Distributions (default: all)")
    parser.add_argument("--comp", default=['main'], nargs='+', help="Components main, universe, contrib, non-free, non-free-firmware etc. (default: main)")
    parser.add_argument("--build", default=['binary-amd64', 'source'], nargs='+', \
        help="Build binary-amd64, binary-arm64, source etc. (default: binary-amd64 source)")
    parser.add_argument("--force", action="store_true", help="Force update even if remote files are older")
    parser.add_argument("--hold", action="store_true", help="Do not attempt to update metadata")
    parser.add_argument("--find", action="store_true", \
        help="Read stdin and find a minimum version index packages that satisfies the conditions, \
        example: libpython3.13 (>= 3.13.0~rc3)")
    parser.add_argument("--earliest", action="store_true", help="Display the oldest version that matches the criteria")
    parser.add_argument("--latest", action="store_true", help="Display the newest version that matches the criteria")
    parser.add_argument("--source", action="store_true", help="Use the Source field for searching, not the Package field")
    parser.add_argument("--briefly", action="store_true", help="Display only basic fields")
    parser.add_argument("--log-level", default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
        help='Set the logging level (default: %(default)s)')

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')
    status_file = args.local_dir + "/status"

    if args.base_url:
        try:
            with open(status_file, "r") as f:
                saved_status = json.load(f)
                if args.base_url != saved_status['base_url'] or args.comp != saved_status['comp']:
                    logging.error(f"Saved base_url and components: {saved_status['base_url']} {saved_status['comp']}")
                    logging.error(f"New base_url and components: {args.base_url} {args.comp}")
                    logging.error("New options detected. Please remove metadata and repeat or use new --local-dir.")
                    return
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.error(f"Try deleting the file status: {status_file}")
            return
    if not args.base_url:
        try:
            with open(status_file, "r") as f:
                saved_status = json.load(f)
                args.base_url = saved_status['base_url']
                args.comp = saved_status['comp']
        except FileNotFoundError:
            logging.error("Status file missing, base url required")
            return
        except Exception as e:
            logging.error(f"Try deleting the file status: {status_file}")
            return
    if not args.base_url.endswith("/"):
        args.base_url += "/"
    if not args.dist:
        args.dist = None

    selection = None
    if args.latest: selection = "latest"
    elif args.earliest: selection = "earliest"

    apt_pkg.init()

    session = requests.Session()

    if not args.hold:
        if original_metadata_is_newer(args.base_url, args.local_dir, session) or args.force or \
                not os.path.exists(status_file):
            logging.info("Starting metadata update...")
            update_metadata(args.base_url, args.local_dir, args.dist, args.comp, ['binary-amd64', 'source'], session)
            logging.info("Metadata update completed!")
    if args.find:
        find_versions(sys.stdin, args.local_dir + "/index.json", args.dist, args.build, args.briefly, \
            "package" if not args.source else "source", selection)


if __name__ == "__main__":
    main()