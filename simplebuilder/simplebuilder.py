#!/usr/bin/env python3

import argparse
import logging
import os
import glob
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

def run_command(cmd, cwd=None, env=None):
    """Run a shell command and return success status."""
    logging.debug(f"Running command: {cmd} in {cwd}")
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, env=env,
                              capture_output=True, text=True, check=True)
        logging.debug(f"Command output: {result.stdout}")
        if result.stderr:
            logging.debug(f"Command stderr: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e}")
        logging.error(f"Error output: {e.stderr}")
        return False

def scan_packages(repo_path):
    """Run dpkg-scanpackages to update local repository."""
    if len(os.listdir(repo_path)) == 0:
        logging.info(f"Repository folder is empty {repo_path}")
        return
    logging.info(f"Scanning packages in {repo_path}")
    run_command("dpkg-scanpackages . > Packages", cwd=repo_path)
    run_command("dpkg-scansources . > Sources", cwd=repo_path)
    update_packages()

def update_packages():
    logging.info("Update packages")
    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    env['NEEDRESTART_MODE'] = 'a'  # Auto restart mode
    env['DEBCONF_NOWARNINGS'] = 'yes'
    run_command("apt-get update && apt-get -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef -y upgrade", env=env)

def clone_and_build_gbp(repo_url, build_dir, repo_dir):
    """Clone and build with gbp-buildpackage."""
    logging.info(f"Cloning and building with gbp-buildpackage: {repo_url}")

    # Extract repo name from URL
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    clone_dir = os.path.join(build_dir, repo_name)

    # Clone repository
    if not run_command(f"git clone {repo_url} {repo_name}", cwd=build_dir):
        return False

    run_command("yes | mk-build-deps -i -r debian/control", cwd=build_dir)

    # Build with gbp-buildpackage
    if run_command("gbp buildpackage -uc -us --git-no-pristine-tar --git-ignore-new", cwd=clone_dir):
        # Copy built packages to repository
        return copy_built_packages(clone_dir, repo_dir)
    return False

def download_and_build_dpkg(url, build_dir, repo_dir, rebuild=False):
    """Download and build with dpkg-buildpackage."""
    logging.info(f"Downloading and building: {url}")

    with tempfile.TemporaryDirectory(dir=build_dir) as temp_dir:
        # Download file
        filename = url.split('/')[-1]
        local_path = os.path.join(temp_dir, filename)

        if not run_command(f"dget {url}", cwd=temp_dir):
            return False

        # Find extracted directory
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if os.path.isdir(item_path) and item != filename:
                build_cmd = "dpkg-buildpackage -uc -us"
                if rebuild:
                    # Add version bump for rebuild
                    build_cmd = "DEB_BUILD_OPTIONS='nocheck' dpkg-buildpackage -uc -us -b --build=full"

                run_command("yes | mk-build-deps -i -r debian/control", cwd=item_path)
                if run_command(build_cmd, cwd=item_path):
                    return copy_built_packages(temp_dir, repo_dir)
                break

    return False

def copy_to_repo(file_url, repo_dir):
    """Copy file to repository using wget for URLs."""
    logging.info(f"Copying to repository: {file_url}")

    if file_url.startswith(('http://', 'https://')):
        # Use wget for HTTP/HTTPS URLs
        try:
            result = subprocess.run(
                ['wget', '-q', '-P', repo_dir, file_url],
                capture_output=True,
                text=True,
                check=True
            )
            logging.info(f"Successfully downloaded: {file_url}")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to download {file_url}: {e}")
            return False
    else:
        local_path = file_url[7:] if file_url.startswith('file://') else file_url
        if os.path.exists(local_path):
            shutil.copy2(local_path, repo_dir)
            logging.info(f"Successfully copied: {local_path}")
            return True
        else:
            logging.error(f"File not found: {local_path}")
            return False

def copy_built_packages(source_dir, repo_dir):
    copied = False
    for file in os.listdir(source_dir):
        if file.endswith(('.deb', '.dsc', '.tar.gz', '.tar.xz')):
            shutil.copy2(os.path.join(source_dir, file), repo_dir)
            logging.info(f"Copied {file} to repository")
            copied = True

    if not copied:
        logging.warning("No files found to copy")
    return copied

def process_line(line, args):
    """Process a single input line."""
    line = line.strip()
    if not line or line.startswith('#'):
        return True  # Skip empty lines

    # Extract URL and comment
    if '#' in line:
        url_part, comment = line.split('#', 1)
        url_part = url_part.strip()
        comment = comment.strip()
    else:
        url_part = line
        comment = ""

    if not url_part:
        return True  # Skip lines with only comments

    url = url_part
    logging.info(f"Processing: {url} (comment: '{comment}')")

    # Ensure directories exist
    os.makedirs(args.build, exist_ok=True)
    os.makedirs(args.repository, exist_ok=True)

    success = False

    try:
        if url.endswith('.git'):
            # Git repository - clone and build with gbp-buildpackage
            success = clone_and_build_gbp(url, args.build, args.repository)
            if success:
                success = scan_packages(args.repository)

        elif url.endswith('.dsc'):
            # Source package
            if 'rebuild' in comment.lower():
                # Rebuild with version bump
                success = download_and_build_dpkg(url, args.build, args.repository, rebuild=True)
            else:
                # Normal build
                success = download_and_build_dpkg(url, args.build, args.repository, rebuild=False)

            if success:
                success = scan_packages(args.repository)

        elif url.endswith('.deb'):
            # Binary package - copy to repository
            success = copy_to_repo(url, args.repository)

        else:
            logging.warning(f"Unknown file type: {url}")
            return False

        if success:
            logging.info(f"Successfully processed: {url}")
        else:
            logging.error(f"Failed to process: {url}")

        return success

    except Exception as e:
        logging.error(f"Error processing {url}: {e}")
        return False

def deb_src_apt_sources():
    # Path to the sources.list.d directory
    sources_dir = '/etc/apt/sources.list.d/'

    # Find all files in the directory
    pattern = os.path.join(sources_dir, '*')
    files = glob.glob(pattern)

    for file_path in files:
        # Skip directories, only process files
        if os.path.isfile(file_path):
            try:
                # Read the file content
                with open(file_path, 'r') as f:
                    content = f.read()

                # Replace 'Types: deb' with 'Types: deb deb-src'
                updated_content = content.replace('Types: deb', 'Types: deb deb-src')

                # If content changed, write it back
                if updated_content != content:
                    with open(file_path, 'w') as f:
                        f.write(updated_content)
                    print(f"Updated: {file_path}")
                else:
                    print(f"No changes needed: {file_path}")

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

def add_local_repo_sources(repo_path):
    """Add local repository to apt sources using pure Python"""
    repo_entry = f'''
        deb [trusted=yes] file://{os.path.abspath(repo_path)} ./
        deb-src [trusted=yes] file://{os.path.abspath(repo_path)} ./
    '''
    sources_file = "/etc/apt/sources.list.d/simplebuilder.list"
    with open(sources_file, 'w') as f:
        f.write(repo_entry + '\n')
        logging.info("Successfully added local repository to sources")

def remove_local_repo_sources():
    """Remove local repository from apt sources"""
    sources_file = "/etc/apt/sources.list.d/simplebuilder.list"
    if os.path.exists(sources_file):
        os.remove(sources_file)
        logging.info("Successfully removed local repository from sources")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Simple debbuild system with stdin job flow")
    parser.add_argument("--workspace", default="/tmp/workspace", help="Local workspace (default: %(default)s)")
    parser.add_argument("--repository", default="/tmp/workspace/repository", help="Local repository (default: %(default)s)")
    parser.add_argument("--build", default="/tmp/workspace/build", help="Local build folder (default: %(default)s)")
    parser.add_argument("--filtering-pkgs", type=str, metavar='PATH', help="File containing a list of filtering packets for the apt manager")
    parser.add_argument("--log-level", default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
        help='Set the logging level (default: %(default)s)')

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    # Create workspace directories
    os.makedirs(args.workspace, exist_ok=True)
    os.makedirs(args.repository, exist_ok=True)
    os.makedirs(args.build, exist_ok=True)

    deb_src_apt_sources()
    update_packages()
    add_local_repo_sources(args.repository)

    logging.info(f"Starting build process. Workspace: {args.workspace}, Repository: {args.repository}")

    # Read from stdin
    success_count = 0
    fail_count = 0

    for line_num, line in enumerate(sys.stdin, 1):
        line = line.strip()
        if not line:
            continue

        logging.info(f"Processing line {line_num}: {line}")

        if process_line(line, args):
            success_count += 1
        else:
            fail_count += 1

    logging.info(f"Build process completed. Success: {success_count}, Failed: {fail_count}")

    remove_local_repo_sources()

    if fail_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
