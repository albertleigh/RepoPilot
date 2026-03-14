"""Build script for creating standalone RepoPilot executable.
Uses PyInstaller to package client + core into a single .exe.
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
    for spec_file in ['RepoPilot.spec']:
        if os.path.exists(spec_file):
            os.remove(spec_file)


def build_application():
    """Build integrated application executable"""
    icon_path = Path("assets/repopilot.ico")
    icon_flag = f'--icon="{icon_path}" ' if icon_path.exists() else ""
    cmd = (
        "pyinstaller --onefile --windowed "
        "--name=RepoPilot "
        f"{icon_flag}"
        '--add-data="assets;assets" '
        '--paths="." '
        '--paths="client" '
        "--hidden-import=PySide6.QtCore "
        "--hidden-import=PySide6.QtGui "
        "--hidden-import=PySide6.QtWidgets "
        "--hidden-import=core "
        "--hidden-import=core.context "
        "--hidden-import=core.events "
        "--hidden-import=core.events.event_bus "
        "--hidden-import=core.events.event_types "
        "--hidden-import=core.engineer_manager "
        "--hidden-import=core.project_manager "
        "--hidden-import=core.LLMClients "
        "--hidden-import=core.LLMClients.claude_on_azure "
        "--hidden-import=core.LLMClients.gpt5_on_azure "
        "--hidden-import=core.LLMClients.gpt5_codex_on_azure "
        "--hidden-import=core.LLMClients.kimi_k2_thinking_on_azure "
        "--hidden-import=core.mcp "
        "--hidden-import=core.skills "
        "--hidden-import=core.repo_registry "
        "--hidden-import=core.git_utils "
        "--hidden-import=anthropic "
        "--hidden-import=openai "
        "--hidden-import=markdown "
        "--collect-submodules=PySide6 "
        "--collect-submodules=core "
        "--exclude-module=PySide6.scripts "
        "client/main.py"
    )
    run_command(cmd, "Building RepoPilot")


def create_release_package():
    """Create a release folder with executable and configs"""
    release_dir = Path("release")
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir()
    
    print(f"\n📦 Creating release package...")
    
    # Copy executable
    shutil.copy("dist/RepoPilot.exe", release_dir / "RepoPilot.exe")
    
    # Create README for release
    readme_content = """# RepoPilot - Release Package

## Contents
- RepoPilot.exe - Main application

## How to Run

Double-click `RepoPilot.exe` to launch the application.

## First-Time Setup

1. Click + in the LLM Clients panel to configure your LLM provider.
2. Click + in the Repositories panel to add a codebase.
3. Right-click a repo and choose Start Engineer to begin.

## Notes
- User data is stored in %APPDATA%/RepoPilot.
- No network relay - LLM calls go directly from your machine to the provider API.
- Standalone executable with no external dependencies.
"""
    
    with open(release_dir / "README.txt", "w") as f:
        f.write(readme_content)
    
    print(f"✅ Release package created in: {release_dir.absolute()}")


def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║     RepoPilot - Build Script                              ║
║     Building standalone executable with PyInstaller        ║
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
  ✓ RepoPilot.exe     - RepoPilot application
  ✓ README.txt        - User instructions

To distribute: Zip the 'release' folder and share!
""")


if __name__ == "__main__":
    main()
