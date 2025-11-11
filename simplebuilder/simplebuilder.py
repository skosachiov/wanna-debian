#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import glob
from pathlib import Path
from datetime import datetime
import re
import logging

# Configuration
WORK_DIR = Path("/workspace")
REPO_DIR = WORK_DIR / "repository"
BUILD_DIR = WORK_DIR / "build"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def log(message: str):
    logger.info(message)

def error(message: str):
    logger.error(f"[ERROR] {message}")

def warning(message: str):
    logger.warning(f"[WARNING] {message}")

def success(message: str):
    logger.info(f"[SUCCESS] {message}")

def run_command(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> bool:
    """Run a shell command and return success status."""
    try:
        log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
        if result.returncode != 0:
            error(f"Command failed: {result.stderr}")
            return False
        return True
    except subprocess.CalledProcessError as e:
        error(f"Command failed with exit code {e.returncode}: {e.stderr}")
        return False
    except Exception as e:
        error(f"Error running command: {e}")
        return False

def init_repository():
    """Initialize the repository structure."""
    log("Initializing repository structure")
    
    (REPO_DIR / "conf").mkdir(parents=True, exist_ok=True)
    (REPO_DIR / "pool" / "main").mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    
    distributions_file = REPO_DIR / "conf" / "distributions"
    if not distributions_file.exists():
        distributions_file.write_text("""Codename: trixie
Suite: stable
Version: 13.0
Architectures: amd64 arm64 armhf i386 source
Components: main
Description: Debian package repository
SignWith: yes
Pull: trixie
""")
    
    options_file = REPO_DIR / "conf" / "options"
    if not options_file.exists():
        options_file.write_text("""verbose
basedir .
ask-passphrase
""")

def install_build_deps(control_file: Path) -> bool:
    """Install build dependencies from a debian/control file."""
    if not control_file.exists():
        warning(f"Control file not found: {control_file}")
        return True
    
    log("Installing build dependencies")
    
    # First update package lists
    if not run_command(["sudo", "apt-get", "update"]):
        warning("Failed to update package lists")
    
    # Install build dependencies
    result = run_command([
        "sudo", "mk-build-deps", "-i", "-r", "-t", "apt-get -y", str(control_file)
    ], check=False)
    
    if not result:
        warning("Failed to install some build dependencies, continuing anyway")
    
    return True

def download_dsc_file(url: str) -> Optional[Path]:
    """Download a .dsc file and related files using dget."""
    log(f"Downloading .dsc file: {url}")
    
    os.chdir(BUILD_DIR)
    
    if run_command(["dget", "-x", url]):
        # Find the downloaded .dsc file
        dsc_files = list(BUILD_DIR.glob("*.dsc"))
        if dsc_files:
            return dsc_files[0]
        else:
            error("No .dsc file found after download")
    
    return None

def get_package_name_from_dsc(dsc_file: Path) -> str:
    """Extract package name from .dsc file."""
    try:
        # Try to get source package name from dsc file
        result = subprocess.run(
            ["dpkg-source", "-f", str(dsc_file)],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("Source:"):
                return line.split(":", 1)[1].strip()
    except subprocess.CalledProcessError:
        pass
    
    # Fallback: derive from filename
    name = dsc_file.stem
    if "_" in name:
        name = name.split("_")[0]
    return name

def build_from_dsc(url: str) -> bool:
    """Build package from .dsc file."""
    log(f"Building from .dsc: {url}")
    
    # Download .dsc file
    dsc_file = download_dsc_file(url)
    if not dsc_file:
        return False
    
    # Get package name
    package_name = get_package_name_from_dsc(dsc_file)
    log(f"Building package: {package_name}")
    
    # Extract source
    extract_dir = BUILD_DIR / f"{package_name}-build"
    if run_command(["dpkg-source", "-x", str(dsc_file), str(extract_dir)]):
        os.chdir(extract_dir)
        
        # Install build dependencies
        control_file = extract_dir / "debian" / "control"
        install_build_deps(control_file)
        
        # Build binary packages
        log("Running dpkg-buildpackage")
        if run_command(["dpkg-buildpackage", "-us", "-uc", "-b"]):
            return copy_built_packages(package_name)
    
    return False

def clone_or_update_git_repo(url: str, repo_name: str) -> Optional[Path]:
    """Clone or update a git repository."""
    repo_dir = BUILD_DIR / repo_name
    
    if repo_dir.exists():
        log(f"Repository already exists, updating: {repo_name}")
        os.chdir(repo_dir)
        # Try different default branches
        for branch in ["main", "master"]:
            if run_command(["git", "pull", "origin", branch], check=False):
                return repo_dir
        warning("Could not update repository, using existing code")
    else:
        log(f"Cloning repository: {url}")
        if run_command(["git", "clone", url, str(repo_dir)]):
            return repo_dir
    
    return None

def build_from_git(url: str) -> bool:
    """Build package from git repository."""
    log(f"Building from git repository: {url}")
    
    # Extract repository name
    repo_name = Path(url).stem
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    
    # Clone/update repository
    repo_dir = clone_or_update_git_repo(url, repo_name)
    if not repo_dir:
        return False
    
    os.chdir(repo_dir)
    
    # Check for Debian packaging files
    debian_dir = repo_dir / "debian"
    control_file = debian_dir / "control"
    rules_file = debian_dir / "rules"
    
    if not rules_file.exists():
        error("No Debian packaging files found in repository")
        return False
    
    # Install build dependencies
    if control_file.exists():
        install_build_deps(control_file)
    
    # Build package
    log("Running dpkg-buildpackage")
    if run_command(["dpkg-buildpackage", "-us", "-uc", "-b"]):
        return copy_built_packages(repo_name)
    
    return False

def copy_built_packages(package_name: str) -> bool:
    """Copy built packages to repository pool."""
    log("Copying built packages to repository")
    
    # Create pool directory structure
    first_letter = package_name[0].lower()
    pool_dir = REPO_DIR / "pool" / "main" / first_letter / package_name
    pool_dir.mkdir(parents=True, exist_ok=True)
    
    os.chdir(BUILD_DIR)
    
    # Copy various package files
    file_patterns = ["*.deb", "*.changes", "*.dsc", "*.buildinfo"]
    copied_files = []
    
    for pattern in file_patterns:
        for file_path in BUILD_DIR.glob(pattern):
            if file_path.is_file():
                log(f"Copying: {file_path.name}")
                shutil.copy2(file_path, pool_dir)
                copied_files.append(file_path.name)
    
    if not copied_files:
        warning("No package files found to copy")
        return False
    
    success(f"Copied {len(copied_files)} files for package: {package_name}")
    return True

def update_repository() -> bool:
    """Update repository index with reprepro."""
    log("Updating repository index")
    
    os.chdir(REPO_DIR)
    
    # Check if we have any .deb files
    deb_files = list(REPO_DIR.glob("pool/main/*/*/*.deb"))
    if not deb_files:
        warning("No binary packages found to include in repository")
        return True
    
    log(f"Found {len(deb_files)} binary packages to include")
    
    # Include all binary packages
    success_count = 0
    for deb_file in deb_files:
        log(f"Including package: {deb_file.name}")
        if run_command(["reprepro", "includedeb", "trixie", str(deb_file)], check=False):
            success_count += 1
        else:
            warning(f"Failed to include: {deb_file.name}")
    
    # Include source packages if present
    dsc_files = list(REPO_DIR.glob("pool/main/*/*/*.dsc"))
    for dsc_file in dsc_files:
        log(f"Including source: {dsc_file.name}")
        run_command(["reprepro", "includedsc", "trixie", str(dsc_file)], check=False)
    
    # Export repository
    run_command(["reprepro", "export"], check=False)
    
    # List packages in repository
    run_command(["reprepro", "list", "trixie"], check=False)
    
    if success_count > 0:
        success(f"Repository updated successfully with {success_count} packages")
        return True
    else:
        error("No packages were successfully added to repository")
        return False

def clean_build_directory():
    """Clean the build directory."""
    log("Cleaning build directory")
    os.chdir(BUILD_DIR)
    
    # Remove all files and subdirectories in build directory
    for item in BUILD_DIR.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

def process_url(url: str) -> bool:
    """Process a single URL (DSC or Git repository)."""
    log(f"Processing: {url}")
    
    url = url.strip()
    
    # Skip empty lines and comments
    if not url or url.startswith('#'):
        return True
    
    if url.endswith('.dsc'):
        return build_from_dsc(url)
    elif '.git' in url or url.startswith(('http://', 'https://', 'git@')):
        return build_from_git(url)
    else:
        error(f"Unknown URL type: {url}")
        return False

def main():
    """Main function."""
    log("Starting package builder")
    
    # Initialize repository structure
    init_repository()
    
    # Update system package lists
    log("Updating system package lists")
    run_command(["sudo", "apt-get", "update"], check=False)
    
    # Read URLs from stdin
    urls = []
    for line in sys.stdin:
        line = line.strip()
        if line and not line.startswith('#'):
            urls.append(line)
    
    if not urls:
        error("No URLs provided via stdin")
        sys.exit(1)
    
    log(f"Processing {len(urls)} URLs")
    
    # Process each URL
    success_count = 0
    failed_count = 0
    
    for url in urls:
        if process_url(url):
            # Update repository after each successful build
            if update_repository():
                success_count += 1
                success(f"Package built and repository updated: {url}")
            else:
                warning(f"Package built but repository update had issues: {url}")
                success_count += 1  # Still count as success for build
        else:
            failed_count += 1
            error(f"Failed to build package: {url}")
        
        # Clean build directory for next package
        clean_build_directory()
    
    # Final repository update
    log("Performing final repository update")
    update_repository()
    
    # Summary
    log(f"Build summary: {len(urls)} total, {success_count} successful, {failed_count} failed")
    
    if failed_count > 0:
        error("Some packages failed to build")
        sys.exit(1)
    else:
        success("All packages built successfully")
        sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        error("Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        error(f"Unexpected error: {e}")
        sys.exit(1)