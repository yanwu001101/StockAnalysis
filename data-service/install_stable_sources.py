#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Install and verify the stable data source system.

This script:
1. Checks Python version
2. Installs required dependencies
3. Runs basic smoke tests
4. Provides next steps
"""
import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Ensure Python 3.8+."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"✗ Python 3.8+ required, found {version.major}.{version.minor}")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True


def install_dependencies():
    """Install required packages."""
    print("\n" + "=" * 80)
    print(" Installing Dependencies")
    print("=" * 80)

    packages = [
        "httpx>=0.27.0",
        "tenacity>=8.2.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
    ]

    for pkg in packages:
        print(f"\nInstalling {pkg}...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", pkg],
                stdout=subprocess.DEVNULL,
            )
            print(f"✓ {pkg}")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {pkg}: {e}")
            return False

    return True


def verify_imports():
    """Verify all modules can be imported."""
    print("\n" + "=" * 80)
    print(" Verifying Imports")
    print("=" * 80)

    modules = [
        ("httpx", "HTTPX async client"),
        ("tenacity", "Retry library"),
        ("pydantic", "Data validation"),
        ("pydantic_settings", "Settings management"),
    ]

    for module, desc in modules:
        try:
            __import__(module)
            print(f"✓ {module:<20} ({desc})")
        except ImportError as e:
            print(f"✗ {module:<20} - {e}")
            return False

    return True


def run_smoke_test():
    """Run a quick smoke test."""
    print("\n" + "=" * 80)
    print(" Running Smoke Tests")
    print("=" * 80)

    try:
        # Test 1: Import aggregator
        print("\n[1/3] Testing aggregator import...")
        from sources.aggregator import default_aggregator
        print("✓ Aggregator imported")

        # Test 2: Import enhanced cache
        print("\n[2/3] Testing enhanced cache...")
        from cache_enhanced import enhanced
        cache = enhanced()
        print("✓ Enhanced cache imported")

        # Test 3: Import health checker
        print("\n[3/3] Testing health checker...")
        from core import health
        checker = health.default()
        print("✓ Health checker imported")

        print("\n✓ All smoke tests passed!")
        return True

    except Exception as e:
        print(f"\n✗ Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 80)
    print(" Stable Data Source System - Installation")
    print("=" * 80)

    # Step 1: Check Python version
    print("\n[Step 1/4] Checking Python version...")
    if not check_python_version():
        sys.exit(1)

    # Step 2: Install dependencies
    print("\n[Step 2/4] Installing dependencies...")
    if not install_dependencies():
        print("\n✗ Dependency installation failed")
        sys.exit(1)

    # Step 3: Verify imports
    print("\n[Step 3/4] Verifying imports...")
    if not verify_imports():
        print("\n✗ Import verification failed")
        sys.exit(1)

    # Step 4: Smoke test
    print("\n[Step 4/4] Running smoke tests...")
    if not run_smoke_test():
        print("\n✗ Smoke tests failed")
        sys.exit(1)

    # Success!
    print("\n" + "=" * 80)
    print(" Installation Complete!")
    print("=" * 80)
    print("\n📋 Next Steps:\n")
    print("1. Run full test suite:")
    print("   python test_data_stability.py")
    print()
    print("2. Enable in your application:")
    print("   python enable_stable_sources.py --mode enable")
    print()
    print("3. Or use directly in code:")
    print("   from data_service_v2 import fetch_spot, fetch_kline")
    print("   spot = fetch_spot()")
    print()
    print("4. Monitor health:")
    print("   curl http://localhost:5001/api/data-sources/health")
    print()
    print("📖 Documentation:")
    print("   - Quick start: QUICKSTART.md")
    print("   - Full guide:  UPGRADE_GUIDE.md")
    print()


if __name__ == "__main__":
    main()
