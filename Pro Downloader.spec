# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
project_dir = Path.cwd()
icon_path = project_dir / "assets" / "pro-downloader.ico"
version_path = project_dir / "packaging" / "windows" / "version_info.txt"

a = Analysis(
    ["reclip_desktop/__main__.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        ("vendors/douyin_downloader", "vendors/douyin_downloader"),
        ("assets/pro-downloader.ico", "assets"),
    ],
    hiddenimports=[
        "yt_dlp",
        "imageio_ffmpeg",
        "curl_cffi",
        "aiohttp",
        "aiofiles",
        "aiosqlite",
        "yaml",
        "rich",
        "gmssl",
        "playwright",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pro Downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
    version=str(version_path),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Pro Downloader",
)
