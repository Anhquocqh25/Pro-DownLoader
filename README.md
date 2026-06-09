# Pro Downloader

<p align="center">
  <img src="assets/pro-downloader.png" width="128" alt="Pro Downloader icon">
</p>

Windows desktop downloader and installable mobile PWA powered by `yt-dlp`,
with dedicated TikTok and Douyin fallback providers.

## Download

Download the latest Windows installer from:

**[GitHub Releases](https://github.com/Anhquocqh25/pro-downloader/releases/latest)**

Run `Pro-Downloader-Setup-1.0.0.exe`, complete the installer, and open
**Pro Downloader** from the Start Menu. Python is not required.

The current installer is not code-signed. Windows SmartScreen may display an
unknown publisher warning until a trusted signing certificate is added.
Verify the installer against the included `SHA256SUMS.txt`.

## Hosted PWA

The 24/7 hosted PWA is available at:

**https://downloader.34-60-0-248.nip.io**

Open **Server settings** and enter the API key configured on the VPS. On
iPhone, use Safari's **Share > Add to Home Screen > Open as Web App** action.

The hosted service:

- Uses HTTPS through Caddy.
- Runs as an isolated systemd service.
- Keeps the API behind an API key.
- Removes downloaded media after 24 hours.

## Features

- Paste one or more URLs and automatically fetch metadata.
- Download video as MP4 or extract audio as MP3.
- Show exact provider and available format/quality choices.
- Try `yt-dlp` first for TikTok, then use TikWM or TikMate when needed.
- Prefer the bundled jiji262 engine for Douyin, with SnapDouyin and `yt-dlp`
  fallback paths.
- Browser cookies, proxy, max quality, subtitles/language, metadata,
  thumbnail, impersonation, and Douyin engine controls.
- Download progress, history/archive, duplicate protection, and open-video
  actions.
- PWA preview, save/share controls, history, install manifest, and service
  worker.

Support for websites outside TikTok and Douyin follows the extractors
available in the bundled `yt-dlp` version. Site changes may require a new
release.

## Source Setup

```powershell
git clone https://github.com/Anhquocqh25/pro-downloader.git
cd pro-downloader
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the desktop app:

```powershell
.\.venv\Scripts\python.exe -m reclip_desktop
```

Downloads default to:

```text
%USERPROFILE%\Downloads\Pro Downloader
```

## Build Windows Installer

Requirements:

- Windows 10/11 x64
- Python 3.10+
- Inno Setup 6

```powershell
.\scripts\build_windows.ps1 `
  -Python .\.venv\Scripts\python.exe `
  -Iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

The build script:

1. Installs build dependencies.
2. Regenerates desktop and PWA icons.
3. Runs the full unit test suite.
4. Builds the standalone PyInstaller application.
5. Builds the Inno Setup installer.
6. Writes `release/SHA256SUMS.txt`.

Tagging a commit with `v*` also runs
`.github/workflows/windows-release.yml` and publishes the installer to a
GitHub Release.

## Run PWA Locally

Double-click:

```text
Start Pro Downloader Server.bat
```

The launcher installs dependencies, configures a local-only firewall rule,
starts the API/PWA, and prints the address to open on an iPhone connected to
the same network.

Default addresses:

```text
PC:     http://127.0.0.1:8000
iPhone: http://YOUR_PC_IP:8000
```

The local launcher uses the development API key `change-me`. Set
`PRO_DOWNLOADER_API_KEY` before launching to override it.

## Deploy PWA to Ubuntu VPS

Clone the repository on the VPS and run:

```bash
sudo bash deploy/vps/install.sh
```

Then add `deploy/vps/Caddyfile.example` to the active Caddy configuration,
replace the example domain, validate the configuration, and reload Caddy.

The deployment uses:

- `/opt/pro-downloader` for application code and its virtual environment.
- `/var/lib/pro-downloader` for runtime state and downloaded media.
- `/etc/pro-downloader.env` for the API key and server configuration.
- `pro-downloader.service` for the API/PWA.
- `pro-downloader-cleanup.timer` for hourly retention cleanup.

Supported environment variables:

```text
PRO_DOWNLOADER_API_KEY=your-secret-key
PRO_DOWNLOADER_HOST=127.0.0.1
PRO_DOWNLOADER_PORT=8000
PRO_DOWNLOADER_DOWNLOAD_DIR=/var/lib/pro-downloader/downloads
PRO_DOWNLOADER_RETENTION_HOURS=24
```

## API

- `GET /api/health`
- `POST /api/fetch`
- `POST /api/download`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/files/{job_id}`
- `GET /api/history`

When an API key is configured, send it in the `X-API-Key` header.

## Project Layout

- `reclip_desktop/`: Windows Tkinter application and downloader core.
- `pro_downloader_server/`: FastAPI server and PWA assets.
- `vendors/douyin_downloader/`: bundled Douyin engine.
- `packaging/windows/`: Windows version metadata and Inno Setup script.
- `deploy/vps/`: systemd, cleanup timer, and Caddy deployment examples.
- `tests/`: downloader and API tests.

## Legal

Download only media you are authorized to access and save. You are
responsible for complying with copyright, platform terms, and local law.

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
