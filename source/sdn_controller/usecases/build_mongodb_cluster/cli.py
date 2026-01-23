#!/usr/bin/env python3
"""
CLI wrapper for MongoDB cluster setup.

This script can be called from build_setup.sh to perform MongoDB initialization
in Python instead of bash.
"""

import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sdn_controller.usecases.build_mongodb_cluster.setup_cluster import setup_mongodb_cluster


def main():
    """Main entry point for the CLI."""
    try:
        success = setup_mongodb_cluster()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nSetup interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during MongoDB cluster setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
