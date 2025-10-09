"""Wrapper for the backport.sh script."""

import os
import subprocess
import sys
from pathlib import Path

def main():
    """Execute the backport.sh script."""
    script_path = Path(__file__).parent / "backport.sh"

    if not script_path.exists():
        print(f"Error: backport.sh not found at {script_path}")
        sys.exit(1)

    # Make sure the script is executable
    script_path.chmod(0o755)

    # Execute the shell script with all arguments
    result = subprocess.run([str(script_path)] + sys.argv[1:])
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()