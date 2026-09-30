# LuminaPhoto 📷✨

LuminaPhoto is a privacy-first, local-first intelligent photo management system. It pairs local computer vision (face recognition, pet detection, EXIF / camera classifier, semantic CLIP search) with automated, conservative Google Drive cloud backup.

---

## 🚀 Key Features

* **Smart Classification:** Automatically distinguishes authentic camera photos from screenshots, web graphics, and icons using hardware EXIF data and aspect-ratio heuristics.
* **Real-Time Folder Watching:** Automatically detects and catalogs new photos added to library folders or imported from SD cards in the background.
* **Mobile Wi-Fi Direct Upload:** Easily upload pictures from your smartphone camera roll directly over your home Wi-Fi into your catalog.
* **People & Pets Detection:** Local on-device detection using YuNet face detection and YOLOv8 pet detection to group and label family, friends, and pets.
* **Duplicate Detection:** Perceptual hash (dHash/pHash) and visual similarity analysis to safely declutter your photo collection.
* **Semantic & Natural Language Search:** Search your library naturally (e.g., *"golden retriever in the snow"* or *"sunset on the beach"*).
* **Automated Database Snapshots:** Crash-safe, lock-free SQLite hot backups with rolling snapshot retention.
* **Conservative Cloud Backup:** Background, rate-limited backup to your own personal Google Drive organized into clean `Year/Month` folders without freezing your connection.

---

## 🔒 Privacy & Google Account Security

LuminaPhoto uses Google's official **OAuth 2.0 Installed Application Flow**:
* **Your Own Account:** The app backs up photos directly to **your personal Google Drive storage**. No files are uploaded to third-party servers.
* **Zero Cost / No Shared Quotas:** Google Drive API usage is completely free under personal Google Cloud quotas. You never share storage quotas or API keys with anyone else.
* **Credentials Kept Local:** The authentication tokens (`token.json`) and client secrets (`credentials.json`) remain solely on your local computer and are ignored by `.gitignore`.

---

## 📋 Prerequisites

* **Python 3.10+**
* **Node.js 18+** & npm
* A free personal **Google Account** (if using Google Drive backup)

---

## ⚡ Quickstart

### 1. Clone the Repository
```bash
git clone https://github.com/Inouye165/photos.git
cd photos
```

### 2. Set Up Backend (Python)
```bash
# Create and activate virtual environment (optional but recommended)
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate

# Install Python dependencies
pip install -r backend/requirements.txt
```

### 3. Set Up Frontend (React + Vite)
```bash
cd frontend
npm install
cd ..
```

### 4. Start the Application

* **Native Desktop App & System Tray (Recommended):**
  Set up shortcuts and desktop dependencies:
  ```powershell
  .\setup_desktop.ps1
  ```
  Or run directly:
  ```powershell
  python start_desktop.py
  ```
  * Double-click the newly created **LuminaPhoto** desktop shortcut to run silently in the background with zero terminal clutter.
  * Right-click the camera icon in your **Windows System Tray** to open the app, toggle auto-start on logon, or view local Wi-Fi URLs for phone access.

* **Browser-Only Mode:**
  ```powershell
  .\start.ps1
  ```

* **Silent Background / Windows Boot Mode:**
  ```powershell
  python start_desktop.py --minimized
  ```

---

## ☁️ Setting Up Google Drive Backup (Step-by-Step)

Because LuminaPhoto is open-source and respects user privacy, each installation connects to Google Drive using your own Google Cloud client credentials. This takes about **3 minutes** to configure:

### Step 1: Create a Google Cloud Project
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown in the top bar and click **New Project**.
3. Name it `LuminaPhoto Backup` (or any name you prefer) and click **Create**.
4. Make sure your newly created project is selected in the top bar dropdown.

### Step 2: Enable the Google Drive API
1. In the search bar at the top, search for **Google Drive API**.
2. Click on **Google Drive API** and click the blue **Enable** button.

### Step 3: Configure the OAuth Consent Screen
1. In the left navigation menu, go to **APIs & Services** > **OAuth consent screen**.
2. Under **User Type**, choose **External** and click **Create**.
3. Fill in the required fields:
   * **App name**: `LuminaPhoto`
   * **User support email**: Select your own email.
   * **Developer contact email**: Enter your own email.
4. Click **Save and Continue** through the *Scopes* step (no manual scope addition required here).
5. In the **Test users** step:
   * Click **+ Add Users** and enter your Google account email address.
   * *(Important: Because the project is in testing mode, only test users can log in).*
6. Click **Save and Continue** and return to the dashboard.

### Step 4: Create Desktop OAuth Client Credentials
1. In the left navigation menu, go to **APIs & Services** > **Credentials**.
2. Click **+ Create Credentials** at the top, then choose **OAuth client ID**.
3. Set **Application type** to **Desktop app**.
4. Name it `LuminaPhoto Desktop` and click **Create**.
5. In the modal that appears, click **Download JSON** (or click the download arrow next to the client in the list).

### Step 5: Place the File in LuminaPhoto
1. Rename the downloaded file to:
   ```text
   credentials.json
   ```
2. Place this file into the `backend/` folder of this project:
   ```text
   photos/
   ├── backend/
   │   ├── credentials.json  <-- Place file here
   │   ├── app.py
   │   └── ...
   ```

### Step 6: Connect in the Web UI
1. Open LuminaPhoto in your browser (`http://localhost:5173`).
2. Click the **Google Drive** icon / pill in the top header.
3. Click **Authorize Google Drive**. Your browser will open asking you to sign in with your Google Account.
4. Once authorized, LuminaPhoto will immediately begin backing up your library in the background!

---

## 🛠️ Backup Rate Limiting & Settings

To prevent overwhelming your network or hitting Google API quotas:
* Uploads are paced with a default **delay between uploads** (30 seconds).
* Uploads adhere to an **hourly quota** (default 25 photos/hour).
* These parameters can be customized at any time via the Backup settings popover in the top navigation bar.

---

## 🗂️ Project Structure

```text
photos/
├── backend/
│   ├── app.py                 # FastAPI REST API endpoints
│   ├── database.py            # SQLite schema, indexing, migrations
│   ├── folder_watcher.py      # Real-time directory watcher & incremental indexer (watchdog)
│   ├── db_backup.py           # SQLite online hot backup & snapshot rotation
│   ├── backup_worker.py       # Background sync worker thread & rate limiting
│   ├── gdrive_auth.py         # Google OAuth 2.0 flow & token management
│   ├── gdrive_service.py      # Google Drive folder hierarchy & upload client
│   ├── classifier.py          # EXIF & camera authentic photo classifier
│   ├── face_pet_detector.py   # Facial recognition & pet detection pipeline
│   ├── deduplicator.py        # Perceptual hash & exact duplicate detection
│   └── desktop/               # Windows desktop integration
│       ├── tray.py            # System Tray icon & context menu (pystray)
│       ├── autostart.py       # Windows Registry logon manager (HKCU Run)
│       ├── window.py          # Native WebView2 application window (pywebview)
│       └── icon.py            # Dynamic Lumina brand icon generator
├── frontend/
│   ├── src/
│   │   ├── components/        # React UI components (Gallery, Backup, Lightbox)
│   │   ├── api.js             # Client API service
│   │   └── App.jsx            # Main app shell
│   └── package.json
├── start_desktop.py           # Unified Desktop & System Tray application runner
├── setup_desktop.ps1          # One-click desktop & start menu shortcut installer
├── LuminaPhoto.bat            # Double-click desktop batch launcher
├── LuminaPhoto.vbs            # Silent launcher without command prompt flash
└── README.md                  # Project documentation & setup instructions
```

---

## 📄 License
MIT License. Open source and free to use.
