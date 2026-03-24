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
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

def run_command(cmd, cwd=None, env=None):
    """Run a shell command and return success status."""
    logging.debug(f"Running command: {cmd} in {cwd}")
    result = None
    with open(os.environ['LOG_FILE'], 'a') as f:
        print(f'Timestamp: {datetime.now().isoformat()}', file=f)
        print(f'Command: {cmd}', file=f)
    cmd = f"set -o pipefail; {cmd} 2>&1 | tee -a {os.environ['LOG_FILE']}"
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, env=env,
                              capture_output=True, text=True, check=True)
        logging.debug(f"Command output: {result.stdout}")
        if result.stderr:
            logging.debug(f"Command stderr: {result.stderr}")
        if result.returncode == 0:
            return True
        else:
            logging.warning(f"Command exit code {result.returncode}")
            return False
    except subprocess.CalledProcessError as e:
        if result and result.returncode != 100:
            logging.warning(f"Command failed: {e}")
        return False

def scan_and_upgrade_packages(repo_path):
    """Run dpkg-scanpackages to update local repository."""
    logging.info(f"Scanning packages in {repo_path}")
    run_command("apt-ftparchive packages . > Packages & dpkg-scansources . > Sources & wait", cwd=repo_path)
    logging.info("Update packages")
    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    env['NEEDRESTART_MODE'] = 'a'  # Auto restart mode
    env['DEBCONF_NOWARNINGS'] = 'yes'
    run_command("apt-get update && apt-get -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef -y upgrade", env=env)

def setup_sbuild_chroot(dist, base_url, extra_repositories, chroot_base="/srv/chroot"):
    """Setup sbuild chroot for building."""
    logging.info(f"Setting up sbuild chroot for {dist}")

    chroot_name = f"{dist}-amd64-sbuild"
    chroot_path = Path(chroot_base) / chroot_name

    # Install sbuild and dependencies
    run_command("apt-get update")
    run_command("apt-get install -y debootstrap schroot sbuild libwww-perl apt-utils")

    # Create debootstrap symlink if needed
    debootstrap_script = Path(f"/usr/share/debootstrap/scripts/{dist}")
    if not debootstrap_script.exists():
        try:
            debootstrap_script.symlink_to("/usr/share/debootstrap/scripts/stable")
        except:
            pass

    # Build extra repository arguments
    extra_repo_args = ""
    if extra_repositories:
        for repo in extra_repositories:
            extra_repo_args += f" --extra-repository='{repo}'"

    # Remove chroot
    if chroot_path.exists():
        logging.info(f"Chroot already exists at {chroot_path}, removing it")
        shutil.rmtree(chroot_path)
    for file_path in glob.glob(f"/etc/schroot/chroot.d/{chroot_name}-*"):
        if os.path.isfile(file_path):
            os.remove(file_path)
            logging.info(f"Removed: {file_path}")

    # Create chroot
    logging.info(f"Create chroot")
    cmd = f"sbuild-createchroot --keyring={os.environ.get('DEB_KEYRING')} \
        --include=ccache {extra_repo_args} {dist} {chroot_path} {base_url}"

    if not run_command(cmd):
        logging.error("Failed to create sbuild chroot")
        return None

    # Fix fstab for /sys
    fstab_path = Path("/etc/schroot/sbuild/fstab")
    if fstab_path.exists():
        content = fstab_path.read_text()
        content = re.sub(r'/sys\s+.*rw,bind', '/sys   /sys   none   rw,rbind   0   0', content)
        fstab_path.write_text(content)

    # Disable HTTPS verification for local builds
    apt_conf_dir = chroot_path / "etc/apt/apt.conf.d"
    apt_conf_dir.mkdir(parents=True, exist_ok=True)
    verify_conf = apt_conf_dir / "99verify-https.conf"
    verify_conf.write_text("""
Acquire::https::Verify-Peer "false";
Acquire::https::Verify-Host "false";
""")

    # Fix permissions for /dev/null
    dev_null = chroot_path / "dev" / "null"
    if dev_null.exists():
        dev_null.chmod(0o777)

    # Add local repository to chroot
    if os.environ.get('LOCAL_REPO_PATH'):
        sources_list = chroot_path / "etc/apt/sources.list"
        repo_line = f"deb [trusted=yes] file://{os.environ['LOCAL_REPO_PATH']} ./"
        with sources_list.open('a') as f:
            f.write(repo_line + '\n')

    logging.info(f"Sbuild chroot created: {chroot_name}")
    return chroot_name

def build_with_sbuild(dsc_url, dist, chroot_name, extra_repositories=None):
    """Build package using sbuild."""
    logging.info(f"Building with sbuild: {dsc_url}")

    # Download .dsc and related files
    with tempfile.TemporaryDirectory() as temp_dir:
        if not run_command(f"dget --allow-unauthenticated {dsc_url}", cwd=temp_dir):
            return False

        # Find .dsc file
        dsc_files = list(Path(temp_dir).glob("*.dsc"))
        if not dsc_files:
            logging.error("No .dsc file found")
            return False

        dsc_file = dsc_files[0]

        # Build sbuild command
        sbuild_cmd = f"sudo -u sbuild sbuild --chroot-mode=schroot -d {dist}"

        # Add extra repositories
        if extra_repositories:
            for repo in extra_repositories:
                sbuild_cmd += f" --extra-repository='{repo}'"

        # Add local repository if exists
        if os.environ.get('LOCAL_REPO_PATH'):
            sbuild_cmd += f" --extra-repository='deb [trusted=yes] file://{os.environ['LOCAL_REPO_PATH']} ./'"

        # Add lintian options to suppress common warnings
        sbuild_cmd += " --lintian-opts='--suppress-tags changelog-distribution-does-not-match-changes-file,bad-distribution-in-changes-file,distribution-and-changes-mismatch'"

        # Add build results directory (the folder containing the dsc file)
        sbuild_cmd += f" --build-results-dir={dsc_file.parent}"

        # Add the dsc file
        sbuild_cmd += f" {dsc_file}"

        # Run sbuild
        if not run_command(sbuild_cmd, cwd=temp_dir):
            logging.error("sbuild failed")
            return False

        # Copy built packages to repository
        sbuild_output = Path(f"/var/lib/sbuild/{chroot_name}")
        if sbuild_output.exists():
            repo_dir = os.environ.get('LOCAL_REPO_PATH', '/tmp/workspace/repository')
            for deb in sbuild_output.glob("*.deb"):
                shutil.copy2(deb, repo_dir)
                logging.info(f"Copied {deb.name} to repository")

        return True

def clone_and_build_gbp(repo_url, build_dir, repo_dir):
    """Clone and build with gbp-buildpackage."""
    logging.info(f"Cloning and building with gbp-buildpackage: {repo_url}")

    # Extract repo name from URL
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    clone_dir = os.path.join(build_dir, repo_name)

    # Clone repository
    if not run_command(f"git clone {repo_url} {repo_name}", cwd=build_dir):
        return False

    logging.info(f"Make and install build dependencies")
    run_command(f"cd {repo_name}; yes | mk-build-deps -i -r debian/control", cwd=build_dir)

    # Build with gbp-buildpackage
    if os.environ['LOCALSUFFIX']:
        run_command(f"cd {repo_name}; dch -v $(dpkg-parsechangelog -S Version){os.environ['LOCALSUFFIX']} 'Add suffix'; \
            git -c user.name={os.environ['DEBFULLNAME']} -c user.email={os.environ['DEBEMAIL']} commit -am 'Add suffix'", \
            cwd=build_dir)

    run_command("gbp buildpackage -uc -us --git-no-pristine-tar --git-ignore-new --git-export-dir=../build-area", cwd=clone_dir)
    # Copy built packages to repository
    rc = copy_built_packages(os.path.join(clone_dir, "../build-area"), repo_dir)
    shutil.rmtree(os.path.join(clone_dir, "../build-area"))
    shutil.rmtree(clone_dir)
    return rc

def download_and_build_dpkg(url, build_dir, repo_dir, rebuild=False):
    """Download and build with dpkg-buildpackage."""
    logging.info(f"Downloading and building: {url}")

    with tempfile.TemporaryDirectory(dir=build_dir) as temp_dir:
        # Download file
        filename = url.split('/')[-1]
        local_path = os.path.join(temp_dir, filename)

        if not run_command(f"dget --allow-unauthenticated {url}", cwd=temp_dir):
            return False

        # Find extracted directory
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if os.path.isdir(item_path) and item != filename:
                if rebuild:
                    build_cmd = "dch --bin-nmu 'Rebuild' && dpkg-buildpackage -uc -us -b"
                    logging.info(f"The required version is present in the repository, bin-nmu rebuild will be used")
                elif os.environ['LOCALSUFFIX']:
                    build_cmd = f"dch -v $(dpkg-parsechangelog -S Version){os.environ['LOCALSUFFIX']} 'Add suffix' \
                        && dpkg-buildpackage -uc -us"
                else:
                    build_cmd = "dpkg-buildpackage -uc -us"

                logging.info(f"Make and install build dependencies")
                run_command("yes | mk-build-deps -i -r debian/control", cwd=item_path)
                run_command(build_cmd, cwd=item_path)
                return copy_built_packages(temp_dir, repo_dir)

    return False

def copy_to_repo(file_url, repo_dir):
    """Copy file to repository using wget for URLs."""
    logging.info(f"Copying to repository: {file_url}")

    if file_url.startswith(('http://', 'https://')):
        # Use wget for HTTP/HTTPS URLs
        try:
            result = subprocess.run(
                ['wget', '-nc', '-q', '-P', repo_dir, file_url],
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
            logging.info(f"Successfully moved: {local_path}")
            return True
        else:
            logging.error(f"File not found: {local_path}")
            return False

def copy_built_packages(source_dir, repo_dir):
    copy_ext = ['.buildinfo', '.changes', '.build']
    deb_files = [f for f in os.listdir(source_dir) if f.endswith('.deb')]
    if deb_files:
        copy_ext.extend(['.deb', '.dsc', '.tar.gz', '.tar.xz', '.tar.bz2', \
            '.tar.gz.asc', '.tar.xz.asc', '.tar.bz2.asc'])
    moved = False
    for file in os.listdir(source_dir):
        if file.endswith(tuple(copy_ext)):
            destination = os.path.join(repo_dir, file)
            if os.path.exists(destination) and os.path.isfile(destination):
                os.remove(destination)
            shutil.move(os.path.join(source_dir, file), repo_dir)
            logging.info(f"Moved {file} to repository")
            if file.endswith('.deb'): moved = True
    if not moved:
        logging.warning("Since no deb files were found, only logs were copied to the repository")
    return moved

def process_line(line, args):
    """Process a single input line."""
    line = line.strip()
    if not line or line.startswith('#'):
        return True  # Skip empty lines

    # Extract URL and comment
    if '#' in line:
        url, comment = line.split('#', 1)
        url = url.strip()
        comment = comment.strip()
    else:
        url = line

    if not url:
        return True  # Skip lines with only comments

    # Ensure directories exist
    os.makedirs(args.build, exist_ok=True)
    os.makedirs(args.repository, exist_ok=True)

    success = False

    try:
        # Convert app name to url
        if '://' not in url:
            result = subprocess.run(['apt', 'source', '--print-uris', url], capture_output=True, text=True, check=True)
            for line in result.stdout.split('\n'):
                if line:
                    line = line.split()[0].strip("'")
                    if line.startswith(('http://', 'https://', 'file:/')) and line.endswith('.dsc'):
                        url = unquote(line)
                        logging.info(f"Package name was converted to a url: {url}")
                        break

        if url.endswith('.git'):
            # Git repository - clone and build with gbp-buildpackage
            success = clone_and_build_gbp(url, args.build, args.repository)
            if success:
                scan_and_upgrade_packages(args.repository)

        elif url.endswith('.dsc'):
            # Check if using sbuild backend
            if args.sbuild:
                # Setup sbuild chroot if needed
                if not hasattr(process_line, 'sbuild_chroot'):
                    process_line.sbuild_chroot = setup_sbuild_chroot(
                        args.dist, args.base_url, args.extra_repository
                    )

                if process_line.sbuild_chroot:
                    success = build_with_sbuild(
                        url, args.dist, process_line.sbuild_chroot, args.extra_repository
                    )
                    if success:
                        scan_and_upgrade_packages(args.repository)
            else:
                # Use traditional dpkg-buildpackage
                match = re.match(r'.*/([^/]+)_(.+)\.dsc$', url)
                if match:
                    package = match.group(1)
                    version = match.group(2)
                # Get state
                src_exists = run_command(f"apt-get source -s {package}={version}{os.environ['LOCALSUFFIX']}")
                bin_exists = run_command(f"apt-cache show \
                    $(apt-cache showsrc {package} | grep ^Binary: | cut -f 2 -d ' ' | cut -f 1 -d ',')={version}{os.environ['LOCALSUFFIX']} \
                    | grep -e '^Version: {version}{os.environ['LOCALSUFFIX']}$' \
                           -e '^Source: {package} ({version}{os.environ['LOCALSUFFIX']})$'")
                if src_exists and bin_exists:
                    logging.warning(f"Skip processing, source and binary package exists: {package}={version}{os.environ['LOCALSUFFIX']}")
                    return None
                rebuild = bin_exists
                # Build or rebuild
                success = download_and_build_dpkg(url, args.build, args.repository, rebuild)
                if success:
                    scan_and_upgrade_packages(args.repository)

        elif url.endswith('.deb'):
            # Binary package - copy to repository
            success = copy_to_repo(url, args.repository)
            if success:
                scan_and_upgrade_packages(args.repository)

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
                updated_content = content.replace('Types: deb\n', 'Types: deb deb-src\n')

                # If content changed, write it back
                if updated_content != content:
                    with open(file_path, 'w') as f:
                        f.write(updated_content)
                    logging.info(f"Updated: {file_path}")
                else:
                    logging.info(f"No changes needed: {file_path}")

            except Exception as e:
                logging.error(f"Error processing {file_path}: {e}")

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

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Simple debbuild system with stdin job flow")
    parser.add_argument("--workspace", default="/tmp/workspace", help="Local workspace (default: %(default)s)")
    parser.add_argument("--repository", default="/tmp/workspace/repository", help="Local repository (default: %(default)s)")
    parser.add_argument("--build", default="/tmp/workspace/build", help="Local build folder (default: %(default)s)")
    parser.add_argument("--profiles", default=["nocheck", "nodoc"], nargs="+", \
        help="Build profiles (default: nocheck nodoc")
    parser.add_argument("--suffix", default='', help="Local suffix (default: %(default)s)")
    parser.add_argument("--log-file", default='simplebuilder.log', help="Log workspace file (default: %(default)s)")
    parser.add_argument("--log-level", default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
        help='Set the logging level (default: %(default)s)')
    parser.add_argument("--sbuild", action="store_true", help="Use sbuild backend for building (default: dpkg-buildpackage)")
    parser.add_argument("--dist", default="stable", help="Distribution for sbuild chroot (default: %(default)s)")
    parser.add_argument("--base-url", default="https://ftp.debian.org/debian",
                       help="Base Debian repository URL for sbuild (default: https://ftp.debian.org/debian)")
    parser.add_argument("--extra-repository", action="append",
                       help="Extra repositories for sbuild (can be specified multiple times)")

    args = parser.parse_args()

    # Create workspace directories
    os.makedirs(args.workspace, exist_ok=True)
    os.makedirs(args.repository, exist_ok=True)
    os.makedirs(args.build, exist_ok=True)

    os.environ['LC_ALL'] = 'C.UTF-8'
    os.environ['LANG'] = 'en_US.UTF-8'
    os.environ['DEBEMAIL'] = os.environ.get('DEBEMAIL', 'simplebuilder@localhost')
    os.environ['DEBFULLNAME'] = os.environ.get('DEBFULLNAME', 'simplebuilder')
    os.environ['LOG_FILE'] = args.workspace + '/' + args.log_file
    os.environ['LOCALSUFFIX'] = args.suffix
    os.environ['DEB_BUILD_OPTIONS'] = " ".join(args.profiles)
    os.environ['LOCAL_REPO_PATH'] = args.repository
    os.environ['DEB_KEYRING'] = os.environ.get('DEB_KEYRING', "/usr/share/keyrings/debian-archive-keyring.gpg")

    logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s', \
        handlers=[logging.StreamHandler(), logging.FileHandler(os.environ['LOG_FILE'])])

    deb_src_apt_sources()
    add_local_repo_sources(args.repository)
    scan_and_upgrade_packages(args.repository)

    logging.info(f"Starting build process. Workspace: {args.workspace}, Repository: {args.repository}")
    if args.sbuild:
        logging.info(f"Using sbuild backend with distribution: {args.dist}, base URL: {args.base_url}")
        if args.extra_repository:
            logging.info(f"Extra repositories: {args.extra_repository}")

    # Read from stdin
    lines = []

    success_count = 0
    fail_count = 0
    skip_count = 0
    success_items = []
    fail_items = []
    skip_items = []

    for line in sys.stdin:
        line = line.strip().split("#")[0]
        if line:
            lines.append(line)

    for line_num, line in enumerate(lines, 1):

        logging.info(f"Processing line {line_num}: {line}")

        os.environ['LOG_FILE'] = args.repository + '/' + line.split('/')[-1] + '.log'
        logging.info(f"The build logs for a specific package: {os.environ['LOG_FILE']}")

        result = process_line(line, args)

        if result is None:
            skip_count += 1
            skip_items.append(line.split('/')[-1])
        elif result:
            success_count += 1
            success_items.append(line.split('/')[-1])
        else:
            fail_count += 1
            fail_items.append(line.split('/')[-1])

        # Remove temporary build-dependencies
        env = os.environ.copy()
        run_command("dpkg -l | grep 'build-dependencies for' | cut -f 3 -d ' ' | xargs -I {} dpkg -r {}", env=env)

        logging.info(f"Statistics on processed: successfully {success_count}, "
            f"unsuccessfully {fail_count}, skip {skip_count}, remaining {len(lines)-line_num}")

    logging.info(f"Build process completed. Success: {success_count}, Failed: {fail_count}, Skip: {skip_count}")
    logging.info(f"Success items: {success_items}")
    logging.warning(f"Failed items: {fail_items}")
    logging.warning(f"Skiped items: {skip_items}")

    logging.info(f"Please note that the local repository remains connected: /etc/apt/sources.list.d/simplebuilder.list")

    if fail_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
