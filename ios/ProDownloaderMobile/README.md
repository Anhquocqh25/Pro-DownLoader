# Pro Downloader Mobile

SwiftUI client for the Pro Downloader backend.

## Setup

1. On your Windows machine, start the backend:

   ```bat
   Start Pro Downloader Server.bat
   ```

2. Find your PC LAN IP:

   ```powershell
   ipconfig
   ```

3. On a Mac with Xcode, create a new iOS App named `ProDownloaderMobile`.
4. Add the Swift files from this folder to the Xcode project.
5. In the app, set:

   - Server: `http://YOUR_PC_IP:8000`
   - API Key: the value printed by `Start Pro Downloader Server.bat`

## Backend API

- `POST /api/fetch`
- `POST /api/download`
- `GET /api/jobs/{job_id}`
- `GET /api/files/{job_id}`
- `GET /api/history`

The API key is sent via the `X-API-Key` header.
