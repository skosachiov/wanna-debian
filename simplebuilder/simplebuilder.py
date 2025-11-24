#!/usr/bin/env python3

import argparse
import logging
import os
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
    logging.info(f"Scanning packages in {repo_path}")
    cmd = f"dpkg-scanpackages . > Packages"
    return run_command(cmd, cwd=repo_path)

def update_packages(filtering_pkgs=None):
    logging.info("Update packages")
    run_command("apt update && apt upgrade")

def clone_and_build_gbp(repo_url, build_dir, repo_dir):
    """Clone and build with gbp-buildpackage."""
    update_packages()

    logging.info(f"Cloning and building with gbp-buildpackage: {repo_url}")

    # Extract repo name from URL
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    clone_dir = os.path.join(build_dir, repo_name)

    # Clone repository
    if not run_command(f"git clone {repo_url} {repo_name}", cwd=build_dir):
        return False

    # Build with gbp-buildpackage
    if run_command("gbp buildpackage -uc -us --git-no-pristine-tar", cwd=clone_dir):
        # Copy built packages to repository
        return copy_built_packages(clone_dir, repo_dir)
    return False

def download_and_build_dpkg(url, build_dir, repo_dir, rebuild=False):
    """Download and build with dpkg-buildpackage."""
    update_packages()

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

                if run_command(build_cmd, cwd=item_path):
                    return copy_built_packages(temp_dir, repo_dir)
                break

    return False

def copy_to_repo(file_url, repo_dir):
    """Copy file to local repository."""
    logging.info(f"Copying file to repository: {file_url}")

    if file_url.startswith('file://'):
        local_path = file_url[7:]  # Remove file:// prefix
    else:
        local_path = file_url

    if os.path.exists(local_path):
        shutil.copy2(local_path, repo_dir)
        return True
    else:
        logging.error(f"File not found: {local_path}")
        return False

def copy_built_packages(source_dir, repo_dir):
    """Copy all .deb files from source directory to repository."""
    copied = False
    for file in os.listdir(source_dir):
        if file.endswith('.deb'):
            shutil.copy2(os.path.join(source_dir, file), repo_dir)
            logging.info(f"Copied {file} to repository")
            copied = True

    if not copied:
        logging.warning("No .deb files found to copy")

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
            if url.startswith('file://'):
                # Local file copy
                success = copy_to_repo(url, args.repository)
            else:
                # Remote file download and copy
                success = copy_to_repo(url, args.repository)
            # No package scanning for copy operations as per requirements

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

def add_local_repo_sources(repo_path):
    """Add local repository to apt sources using pure Python"""
    repo_entry = f"deb [trusted=yes] file:{os.path.abspath(repo_path)} ./"
    sources_file = "/etc/apt/sources.list.d/simplebuilder.list"
    with open(sources_file, 'a') as f:
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
    parser.add_argument("--workspace", default="./workspace", help="Local workspace (default: %(default)s)")
    parser.add_argument("--repository", default="./workspace/repository", help="Local repository (default: %(default)s)")
    parser.add_argument("--build", default="./workspace/build", help="Local build folder (default: %(default)s)")
    parser.add_argument("--filtering-pkgs", type=str, metavar='PATH', help="File containing a list of filtering packets for the apt manager")
    parser.add_argument("--log-level", default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
        help='Set the logging level (default: %(default)s)')

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    # Create workspace directories
    os.makedirs(args.workspace, exist_ok=True)
    os.makedirs(args.repository, exist_ok=True)
    os.makedirs(args.build, exist_ok=True)

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
