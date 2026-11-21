# PyInstaller spec: one folder holding the window, the MCP server and the setup helper, sharing their libraries.
# Build from the repository root: uv run --with pyinstaller pyinstaller packaging/anypoach.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
extension = [(str(root / "src/anypoach/chrome_extension"), "anypoach/chrome_extension")] + copy_metadata("anypoach")
hidden = collect_submodules("anypoach") + collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli"))
excludes = ["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"]

programs = {}
for name, script in (("anypoach", "anypoach_gui.py"), ("anypoach-mcp", "anypoach_mcp.py"),
                     ("anypoach-setup", "anypoach_setup.py")):
    programs[name] = Analysis([str(root / "packaging" / script)], pathex=[str(root / "src")], datas=extension,
                              hiddenimports=hidden, excludes=excludes)

executables, binaries, datas = [], [], []
for name, analysis in programs.items():
    pyz = PYZ(analysis.pure)
    executables.append(EXE(pyz, analysis.scripts, [], exclude_binaries=True, name=name,
                           console=name != "anypoach", icon=None))
    binaries += analysis.binaries
    datas += analysis.datas

collected = COLLECT(*executables, binaries, datas, strip=False, upx=False, name="AnyPoach")
