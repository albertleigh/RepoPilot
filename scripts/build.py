"""
Build script for creating standalone executables
Uses PyInstaller to package client
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*60}")
    print(f"🔨 {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Error during: {description}")
        sys.exit(1)
    print(f"✅ {description} completed successfully")


def clean_build_folders():
    """Remove old build artifacts"""
    folders_to_clean = ['build', 'dist', '__pycache__']
    for folder in folders_to_clean:
        if os.path.exists(folder):
            print(f"🧹 Cleaning {folder}/")
            shutil.rmtree(folder)
    
    # Clean spec files from previous builds if regenerating
    for spec_file in ['qt_app.spec']:
        if os.path.exists(spec_file):
            os.remove(spec_file)


def build_application():
    """Build integrated application executable"""
    cmd = (
        "pyinstaller --onefile --windowed "
        "--name=qt_app "
        "--add-data=\"config.json;.\" "
        "--paths=\".\" "
        "--hidden-import=PySide6.QtCore "
        "--hidden-import=PySide6.QtGui "
        "--hidden-import=PySide6.QtWidgets "
        "--hidden-import=core.services "
        "--collect-submodules=PySide6 "
        "client/main.py"
    )
    run_command(cmd, "Building Application")


def create_release_package():
    """Create a release folder with executable and configs"""
    release_dir = Path("release")
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir()
    
    print(f"\n📦 Creating release package...")
    
    # Copy executable
    shutil.copy("dist/qt_app.exe", release_dir / "qt_app.exe")
    
    # Copy config
    shutil.copy("config.json", release_dir / "config.json")
    
    # Create README for release
    readme_content = """# Qt Python Application - Release Package

## Contents
- qt_app.exe - Main GUI application (integrated)
- config.json - Configuration file

## How to Run

Simply double-click `qt_app.exe` to launch the application!

The application is fully integrated - no separate backend server needed.

## Notes
- All business logic is built into the application
- No network communication required
- Standalone executable with no external dependencies
- You can edit config.json to change settings

## Features
- Check application status
- Get sample data
- Process and store messages
- View response history
"""
    
    with open(release_dir / "README.txt", "w") as f:
        f.write(readme_content)
    
    print(f"✅ Release package created in: {release_dir.absolute()}")


def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║     Qt Python Application - Build Script                  ║
║     Building standalone executables with PyInstaller       ║
╚════════════════════════════════════════════════════════════╝
""")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])
    
    # Clean previous builds
    clean_build_folders()
    
    # Build integrated application
    build_application()
    
    # Create release package
    create_release_package()
    
    print(f"""
╔════════════════════════════════════════════════════════════╗
║                    Build Complete! 🎉                      ║
╚════════════════════════════════════════════════════════════╝

📂 Release files are in: ./release/

Contents:
  ✓ qt_app.exe        - Integrated GUI application
  ✓ config.json       - Configuration
  ✓ README.txt        - User instructions

To distribute: Zip the 'release' folder and share!
Single executable - no backend server needed!
""")


if __name__ == "__main__":
    main()
