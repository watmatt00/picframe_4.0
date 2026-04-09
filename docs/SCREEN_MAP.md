# Screen Map

Single source of truth for all screens/pages across PicFrame Manager (iOS app) and PicFrame Dashboard (web).

## How to Use Screen IDs

Use these stable IDs in test plans, bug reports, and development references:
- `IOS-xxx` - iOS mobile app screens
- `DASH-xxx` - Web dashboard screens/tabs

**Last updated:** 2026-04-09

---

## iOS App Screens

### IOS-SPLASH - Splash Screen

- **File:** `SplashView.swift`
- **Presentation:** App launch (root view via `ContentView.swift` > `SplashView`)
- **UI Elements:**
  - App icon (photo.on.rectangle.angled)
  - "PicFrame" title + "Manager" subtitle
  - Tagline: "Share memories with your frames"
- **Behavior:** Animates in (scale + fade), auto-transitions to IOS-MAIN after 2 seconds
- **Navigation:** Replaces self with `MainContentView` (IOS-MAIN)

---

### IOS-MAIN - Main Content (Root)

- **File:** `MainContentView.swift`
- **Presentation:** Replaces IOS-SPLASH after 2s delay
- **UI Elements:** Wraps IOS-MENU
- **Behavior:** Auto-opens IOS-FRAMES sheet on first launch if no frames are paired
- **Navigation:**
  - `.sheet` > IOS-FRAMES (auto on first launch, no paired frames)

---

### IOS-MENU - Main Menu

- **File:** `MainMenuView.swift`
- **Presentation:** Embedded in IOS-MAIN
- **UI Elements:**
  - Header: App icon, "PicFrame Manager", user email (if connected)
  - Koofr Storage quota card (usage bar, free/used/total)
  - Your Frames summary card (`PairedFramesSummary`):
    - Empty state: "No frames paired. Tap to pair a frame."
    - Populated: Up to 3 frame cards with online status, role badge, current source, sync status, photo counts (frame/cloud), storage info
    - "+ N more" if >3 frames
  - Menu buttons:
    - "Upload Photos" > IOS-UPLOAD
    - "Switch Source" (shows current source name) > IOS-SWITCH
    - "About" > IOS-ABOUT
  - Toolbar: Gear icon > IOS-SETTINGS
- **Conditional States:**
  - With/without Koofr quota
  - With/without paired frames
  - Frame status: loading, loaded, error, idle
  - Sync status badge: In Sync (green), Out of Sync (orange), Syncing (blue), Sync Error (red), Idle (gray)
- **Navigation:**
  - `.fullScreenCover` > IOS-UPLOAD
  - `.sheet` > IOS-SETTINGS
  - `.sheet` > IOS-ABOUT
  - `.sheet` > IOS-FRAMES
  - `.sheet` > IOS-SWITCH

---

### IOS-FRAMES - Frame List

- **File:** `FrameListView.swift`
- **Presentation:** `.sheet` from IOS-MENU or IOS-MAIN
- **UI Elements:**
  - Nav title: "Frames"
  - Toolbar: Done (dismiss), + (add frame)
  - Empty state: Icon, "No Frames Paired", description, "Pair a Frame" button
  - Populated: List of `FrameRow` entries:
    - Frame icon, name, role badge (Admin/Viewer), online/offline dot + label, IP address
    - Swipe-to-delete: "Unpair" action
  - Bottom: "Add Another Frame" button
  - Pull-to-refresh: Rechecks online status
- **Dialogs:**
  - `.confirmationDialog` "Unpair Frame" - destructive unpair with cancel
- **Navigation:**
  - `.sheet` > IOS-PAIR
  - `.fullScreenCover` > IOS-DETAIL

---

### IOS-PAIR - Pairing

- **File:** `PairingView.swift`
- **Presentation:** `.sheet` from IOS-FRAMES
- **UI Elements:**
  - Header: Link icon, "Pair with Frame", instruction text
  - Input fields:
    - Frame IP Address (decimal pad, placeholder "100.x.x.x")
    - Pairing Code (auto-uppercase, max 7 chars, format XXX-XXX)
    - This Device's Name (defaults to `UIDevice.current.name`)
  - Error banner (red background, if pairing fails)
  - "Pair Device" button (shows spinner while pairing)
  - Help section: 4-step instructions for getting a pairing code
  - Toolbar: Cancel (dismiss)
- **Conditional States:**
  - Button disabled until IP, code (>=6 chars), and name filled
  - Loading spinner during pairing
  - Error message display on failure
  - Auto-dismiss on successful pairing

---

### IOS-DETAIL - Frame Detail

- **File:** `FrameDetailView.swift`
- **Presentation:** `.fullScreenCover` from IOS-FRAMES
- **UI Elements:**
  - Status header: Frame icon, online/offline dot, role badge (crown for admin), IP address
  - Error/success message banners
  - Quick actions:
    - "Upload Photos" button > IOS-UPLOAD
    - "Switch Source" button (shows current source) > IOS-SWITCH
  - Capacity card: Storage usage bar, used/free/total
  - Admin-only sections:
    - Services section: List of services with status dot, name, restart button
    - Paired Devices section: Device count, "Manage access" link > IOS-DEVICES
  - Settings section: "Account & Preferences" link > IOS-SETTINGS
  - Toolbar: Close (dismiss), Refresh (arrow.clockwise)
- **Conditional States:**
  - Status loaded vs loading vs error
  - Admin vs viewer role (services and devices sections admin-only)
- **Dialogs:**
  - `.confirmationDialog` "Restart Service" - destructive restart with cancel
- **Navigation:**
  - `.sheet` > IOS-DEVICES
  - `.sheet` > IOS-SETTINGS
  - `.fullScreenCover` > IOS-UPLOAD
  - `.sheet` > IOS-SWITCH

---

### IOS-DEVICES - Device List (Sheet)

- **File:** `FrameDetailView.swift` (embedded as `DeviceListSheet`)
- **Presentation:** `.sheet` from IOS-DETAIL (admin only)
- **UI Elements:**
  - Nav title: "Paired Devices"
  - Toolbar: Done (dismiss)
  - List of devices:
    - iPhone icon, device name, role badge (Admin/Viewer), paired date
    - Swipe action: "Revoke" (destructive)
- **Dialogs:**
  - `.confirmationDialog` "Revoke Access" - destructive revoke with cancel

---

### IOS-SWITCH - Switch Source

- **File:** `DestinationsView.swift` (as `SwitchPhotosView`)
- **Presentation:** `.sheet` from IOS-MENU or IOS-DETAIL
- **UI Elements:**
  - Nav title: "Switch Source"
  - Toolbar: Done (dismiss), + (add source, admin only)
  - Current source header card:
    - "Currently Displaying" label + source name
    - Sync status badge
    - Photo counts: on frame / in cloud
    - Last sync timestamp
    - "Sync Now" button (admin only)
  - Photo Sources list:
    - Source rows: icon (green if active), name, "Active" badge, photo count, path
    - Tapping a source opens IOS-SRCDETAIL
    - "Add New Source" button (admin only)
  - Success/error message sections
  - Pull-to-refresh
- **Conditional States:**
  - No frame paired: "No Frame Paired" empty state
  - Loading: spinner "Loading sources..."
  - Error: "Could Not Load Sources" with Retry button
  - Sources loaded: full source list
- **Navigation:**
  - `.sheet` > IOS-ADDSRC
  - `.sheet` > IOS-SRCDETAIL

---

### IOS-ADDSRC - Add Source (Sheet)

- **File:** `DestinationsView.swift` (embedded as `AddSourceView`)
- **Presentation:** `.sheet` from IOS-SWITCH
- **UI Elements:**
  - Nav title: "Add Source"
  - Form:
    - "New Photo Source" section: Folder Name text field
    - Footer: explanation of what creating a source does
    - "Create Source" button (shows spinner while saving)
  - Error section (if creation fails)
  - Toolbar: Cancel (dismiss)
- **Conditional States:**
  - Button disabled if name empty or saving in progress
  - Auto-dismiss on successful creation

---

### IOS-SRCDETAIL - Source Detail (Sheet)

- **File:** `DestinationsView.swift` (embedded as `SourceDetailView`)
- **Presentation:** `.sheet` from IOS-SWITCH (tapping a source row)
- **UI Elements:**
  - Nav title: Source folder name
  - Toolbar: Done (dismiss)
  - Source Info section: Name, Status (Active/Inactive badge), Photos on Frame count, Path
  - Sync Status section:
    - Loading state: spinner "Loading sync status..."
    - Loaded: Cloud Files count, Local Files count, Sync Status badge, Details message
    - No remote: "No remote configured for sync"
  - Actions section (admin only):
    - "Activate" button (if not active)
    - "Sync Now" button
  - Success/error message sections
- **Conditional States:**
  - Active vs inactive source
  - Sync status loading vs loaded vs no remote
  - Admin vs viewer (actions section)

---

### IOS-UPLOAD - Upload Photos

- **File:** `UploadSheetView.swift`
- **Presentation:** `.fullScreenCover` from IOS-MENU or IOS-DETAIL
- **UI Elements:**
  - Nav title: "Upload Photos"
  - Toolbar: Close (dismiss, clears messages)
  - Destination picker:
    - No destinations: "Koofr Not Connected" card with instructions
    - <=2 destinations: segmented picker
    - >2 destinations: menu picker
    - Selected destination path display
  - "Select Photos" button (PhotosPicker, max 20 images)
  - Selected photos section:
    - Count header + "Clear" button
    - 4-column thumbnail grid
    - "Upload to Koofr" button (shows spinner while uploading)
  - Empty state: "No photos selected" with instructions
  - Upload progress bar: "Uploading X of Y"
  - Success message: "Photos will sync to your frame automatically."
  - Error message display
- **Conditional States:**
  - No Koofr credentials: connection instructions
  - No photos selected: empty state
  - Photos selected: grid + upload button
  - Uploading: progress bar, disabled controls
  - Upload complete: success message

---

### IOS-SETTINGS - Settings

- **File:** `SettingsView.swift`
- **Presentation:** `.sheet` from IOS-MENU or IOS-DETAIL
- **UI Elements:**
  - Nav title: "Settings"
  - Toolbar: Done (dismiss, clears messages)
  - Account section:
    - Connected Account (email or "Not connected")
    - "Test Connection" button (shows spinner)
  - Storage section (if quota available):
    - Usage bar, percent used, free space
  - Frame Actions section (admin only):
    - "Sync Now" button
    - Restart buttons for each service (with status dots)
    - "View Logs" link > IOS-LOGS
  - Sync Settings section (admin only):
    - Sync Interval slider (1-60 minutes)
    - "Save Sync Interval" button
    - Footer: explanation text
  - Danger Zone section:
    - "Change Credentials" button (orange)
    - "Unpair All Frames" button (red, disabled if no frames)
    - "Clear All Data" button (red)
  - Success/error message sections
  - App version footer: "PicFrame Manager v1.0.0"
- **Conditional States:**
  - Admin vs viewer (frame actions and sync settings visible for admin only)
  - Loading settings state for sync interval slider
- **Dialogs:**
  - `.alert` "Unpair All Frames?" - destructive with cancel
  - `.alert` "Clear All Data?" - destructive with cancel
- **Navigation:**
  - `.sheet` > IOS-LOGS

---

### IOS-LOGS - Log Viewer

- **File:** `LogViewerView.swift`
- **Presentation:** `.sheet` from IOS-SETTINGS
- **UI Elements:**
  - Nav title: "Frame Logs"
  - Toolbar: Done (dismiss), Refresh (arrow.clockwise)
  - Log type picker (segmented): Operations / Security
  - Log entries list:
    - Color-coded dots: red (ERROR), orange (WARNING), blue (INFO), gray (other)
    - Monospaced text, max 3 lines per entry
  - Loading state: spinner "Loading logs..."
  - Empty state: "No log entries"
- **Behavior:** Loads 200 lines, reloads on type change or refresh

---

### IOS-ABOUT - About

- **File:** `AboutView.swift`
- **Presentation:** `.sheet` from IOS-MENU
- **UI Elements:**
  - Nav title: "About"
  - Toolbar: Done (dismiss)
  - App icon (blue gradient rounded rectangle with photo icon)
  - "PicFrame Manager" + "Version 1.0.0"
  - About section: App description
  - How It Works section: 4-step numbered list
  - Support section: Contact info + Koofr Web Interface link

---

## iOS Navigation Hierarchy

```
ContentView
  └── SplashView (IOS-SPLASH)
        └── MainContentView (IOS-MAIN)
              ├── [auto .sheet] FrameListView (IOS-FRAMES)  [first launch, no frames]
              └── MainMenuView (IOS-MENU)
                    ├── [.fullScreenCover] UploadSheetView (IOS-UPLOAD)
                    ├── [.sheet] SettingsView (IOS-SETTINGS)
                    │     ├── [.sheet] LogViewerView (IOS-LOGS)
                    │     ├── [.alert] "Unpair All Frames?"
                    │     └── [.alert] "Clear All Data?"
                    ├── [.sheet] AboutView (IOS-ABOUT)
                    ├── [.sheet] FrameListView (IOS-FRAMES)
                    │     ├── [.sheet] PairingView (IOS-PAIR)
                    │     ├── [.fullScreenCover] FrameDetailView (IOS-DETAIL)
                    │     │     ├── [.sheet] DeviceListSheet (IOS-DEVICES)
                    │     │     │     └── [.confirmationDialog] "Revoke Access"
                    │     │     ├── [.sheet] SettingsView (IOS-SETTINGS)
                    │     │     ├── [.fullScreenCover] UploadSheetView (IOS-UPLOAD)
                    │     │     ├── [.sheet] SwitchPhotosView (IOS-SWITCH)
                    │     │     └── [.confirmationDialog] "Restart Service"
                    │     └── [.confirmationDialog] "Unpair Frame"
                    └── [.sheet] SwitchPhotosView (IOS-SWITCH)
                          ├── [.sheet] AddSourceView (IOS-ADDSRC)
                          ├── [.sheet] SourceDetailView (IOS-SRCDETAIL)
                          └── [.alert] "Switch Source"
```

---

## Dashboard Screens

### DASH-STATUS - Frame Status (Tab 1)

- **Files:** `dashboard.html` + `dashboard.js`
- **Presentation:** Default active tab in unified dashboard
- **UI Elements:**

  **Status Banner (top of page, always visible):**
  - Sync status text (e.g., "Photo sync status", "Syncing photos...")
  - Status pill: OK / SYNCING / ERROR / UNKNOWN
  - Last checked timestamp
  - Frame name pill
  - Dynamic background color: green (ok), orange (syncing), red (error), gray (unknown)

  **Overall Status Card:**
  - Status title with sync details (e.g., "Out of sync (15 cloud / 12 local)")
  - Status severity chip
  - Traffic light indicator (green/amber/red, one lit at a time)
  - Count tiles: Cloud photo count, Frame photo count
  - Service grid:
    - Currently Showing: source name
    - Frame Display: status dot + text
    - Dashboard: always "RUNNING"
    - Storage: percent used with progress bar (e.g., "85% (42.5 / 50 GB)")
  - Current image thumbnail (auto-refreshes every 30s)
  - Collapsible advanced details: Source ID, Frame ID

  **Quick Actions Card:**
  - Refresh Dashboard button
  - Sync Now button (shows spinner, confirmation on success)
  - Restart Frame button (confirmation dialog)
  - Restart API button (confirmation dialog, page reloads after 3s)
  - Last sync / last restart timestamps

- **Auto-Refresh:** Status every 15 seconds, thumbnail every 30 seconds
- **Footer:** "Auto-updates every 15 seconds"

---

### DASH-SWITCH - Switch Photos (Tab 2)


- **Files:** `dashboard.html` + `dashboard.js`
- **Presentation:** Tab 2, lazy-initializes on first click
- **UI Elements:**

  **Photo Sources Table:**
  - Columns: ID (tech), Name, Remote, Local Path (tech), Status, Actions (tech)
  - Tech columns toggleable via "Show/Hide technical columns"
  - Status badges: Active (green), Ready (blue), Disabled (gray)
  - Action buttons:
    - Activate (with confirm dialog, triggers sync)
    - Delete (with confirm dialog)

  **Add New Photo Source Form:**
  - Short Name (ID) - text input, alphanumeric/underscore/hyphen validation
  - Display Name - text input
  - Cloud Service - dropdown (loads rclone remotes from API)
  - Cloud Folder Browser:
    - Breadcrumb navigation (Root > folder > subfolder)
    - Clickable directory list
    - Invalid directories shown with warning icon and rename suggestion
  - Local Storage - dropdown (lists ~/Pictures/ directories)
    - Special option: "+ Create new directory" (shows additional name input)
  - Enable checkbox (default: checked)
  - Test Connection button (shows file count on success)
  - Add Photo Source button (confirmation dialog with summary)
  - Status messages (auto-hide success/info after 5s)

---

### DASH-TOOLS - Tools (Tab 3)

- **Files:** `dashboard.html` + `dashboard.js`
- **Presentation:** Tab 3, lazy-initializes on first click
- **UI Elements:**

  **Source Selector** (shared by all tool cards):
  - Dropdown listing all configured photo sources; active source pre-selected

  **Filename Cleaner Card:**
  - Scan button → results table: Preview | ☐ | Original Filename | Proposed Name | EXIF Date | Issues
  - Issues detected: Google ID tokens, numbered dup suffixes, spaces→underscores, long name (>20 chars → renamed to YYYYMMDD_HHMMSS), wrong/uppercase extension
  - Filter bar: All / per-issue type with tooltips
  - Apply Selected Renames button (top + bottom), Cancel button, ✕ Close

  **Duplicate Finder Card:**
  - Scan button → grouped duplicate sets with suggested keeper
  - Delete Duplicates button (top + bottom, destructive red), Cancel, ✕ Close

  **Video File Manager Card:**
  - Scan button → table of video files with sizes
  - Delete Selected Videos button (top + bottom, destructive red), Cancel, ✕ Close

  **Rename File Card:**
  - Scan button (in card header) → table: Preview | Original Filename | EXIF Date | New Filename
  - New Filename inputs are blank by default (original shown as placeholder)
  - Apply Renames button enabled only when at least one name is filled in and all are conflict-free
  - Guardrails: red highlight if proposed name already exists or is used twice in the same batch
  - Apply sends only changed rows via cloud-first rename; table refreshes after success
  - ✕ Close hides results

  **Photo Backups Card** (collapsible via ▸ Show):
  - Create Backup → tar.gz of source's local_path → `~/Pictures/backups/{source_id}_{YYYY-MM-DD_HHMMSS}.tar.gz`
  - Lists existing backups for the selected source (filename, size, created date)
  - Delete button per backup (with confirm dialog)
  - Card auto-collapses 2 seconds after a successful backup

---

### DASH-SETTINGS - Settings (Tab 4)

- **Files:** `dashboard.html` + `dashboard.js`
- **Presentation:** Tab 4
- **UI Elements:**

  **Frame Settings Card:**
  - Frame Name - text input
  - Rotation Interval - number input (5-3600 seconds)
  - Frame ID - read-only input (unique identifier)
  - Funnel URL - read-only input (Tailscale Funnel URL)
  - Sync Interval - number input (1-1440 minutes, converted to seconds for API)
  - Log Level - dropdown (DEBUG, INFO, WARNING, ERROR)
  - Save Settings button (shows "Saving...", updates header frame name on success)
  - Status message (success may include "Frame display restarted")

  **Mobile App Pairing Card:**
  - "Generate Pairing QR Code" button
  - "Manage Devices" toggle button (shows/hides device management card)
  - Inline error display for pairing failures
  - Pairing result section (hidden until generated):
    - QR code image (200x200px)
    - Manual code (large bold text)
    - Countdown timer (seconds until expiry)
    - Connection info: Tailscale IP, Frame URL (if available)
    - Regenerate button
    - How-to-pair instructions (4-step list with security note)
  - Auto-hides when countdown expires

  **Manage Devices Card** (hidden by default, toggled via button):
  - Device table: Name, Role (badge), Paired (date), Last Seen (date), Actions
  - Revoke button per device (AJAX POST with `confirm()` dialog)
  - Empty state: "No devices paired. Use Generate Pairing QR Code above."
  - Device summary: count + admin count (e.g., "3 device(s), 1 admin(s)")
  - Inline status messages for revoke success/error
  - Last-admin protection: Revoke button disabled for sole admin
  - Loads via AJAX: `GET /api/devices`
  - Revoke via AJAX: `POST /devices/{id}/revoke` (returns JSON)

  **Log Viewer Card** (expandable via "Show logs" toggle):
  - Log type dropdown: Operations Log / Security Log
  - Line count dropdown: Last 50 lines / Last 100 lines (default) / Last 500 lines
  - Refresh button
  - Auto-refresh checkbox (5-second interval)
  - Log content: `<pre>` block with monospaced text
  - Loads via AJAX: `GET /api/logs?log_type={ops|security}&lines={50|100|500}`
  - Loads on first expand, reloads on type/count change

---

## Dashboard Navigation

```
Dashboard (single-page, dashboard.html)
  ├── Status Banner (always visible, all tabs)
  ├── Tab 1: Frame Status (DASH-STATUS) [default]
  ├── Tab 2: Switch Photos (DASH-SWITCH) [lazy init]
  ├── Tab 3: Tools (DASH-TOOLS) [lazy init]
  │     ├── Source Selector
  │     ├── Filename Cleaner card
  │     ├── Duplicate Finder card
  │     ├── Video File Manager card
  │     ├── Rename File card
  │     └── Photo Backups card [collapsible]
  └── Tab 4: Settings (DASH-SETTINGS)
        ├── Frame Settings card [collapsible]
        ├── Mobile App Pairing card [collapsible]
        ├── Manage Devices card [toggled via button]
        ├── Log Viewer card [collapsible]
        └── Updates card [collapsible]
```

---

## Feature Cross-Reference

| Feature | iOS Screen | Dashboard Screen |
|---|---|---|
| Sync status overview | IOS-MENU (frame card) | DASH-STATUS |
| Photo counts (frame/cloud) | IOS-MENU, IOS-SWITCH | DASH-STATUS |
| Sync Now | IOS-SWITCH, IOS-SETTINGS, IOS-SRCDETAIL | DASH-STATUS |
| Restart Frame service | IOS-DETAIL, IOS-SETTINGS | DASH-STATUS |
| Restart API service | IOS-SETTINGS | DASH-STATUS |
| View logs (full) | IOS-LOGS | DASH-SETTINGS (expandable log viewer) |
| Source listing | IOS-SWITCH | DASH-SWITCH (table) |
| Switch/activate source | IOS-SWITCH, IOS-SRCDETAIL | DASH-SWITCH (Activate button) |
| Add new source | IOS-ADDSRC | DASH-SWITCH (form) |
| Delete source | -- | DASH-SWITCH (Delete button) |
| Source detail/sync status | IOS-SRCDETAIL | -- |
| Upload photos | IOS-UPLOAD | -- (via Koofr web) |
| Filename cleaning | -- | DASH-TOOLS (Filename Cleaner) |
| Duplicate detection + removal | -- | DASH-TOOLS (Duplicate Finder) |
| Video file management | -- | DASH-TOOLS (Video File Manager) |
| Manual file rename | -- | DASH-TOOLS (Rename File) |
| Local photo backups | -- | DASH-TOOLS (Photo Backups) |
| Frame settings (name, rotation, sync interval, log level) | IOS-SETTINGS (sync interval only) | DASH-SETTINGS |
| Frame ID / Funnel URL (read-only) | -- | DASH-SETTINGS |
| Generate pairing code | -- | DASH-SETTINGS (inline QR + instructions) |
| Enter pairing code | IOS-PAIR | -- |
| Manage paired devices | IOS-DEVICES | DASH-SETTINGS (inline device table) |
| Revoke device access | IOS-DEVICES | DASH-SETTINGS (inline revoke) |
| Software updates | -- | DASH-SETTINGS (Updates card) |
| Koofr storage quota | IOS-MENU, IOS-SETTINGS | -- |
| Frame storage capacity | IOS-MENU, IOS-DETAIL | DASH-STATUS |
| Current image preview | -- | DASH-STATUS (thumbnail) |
| Unpair frames | IOS-FRAMES, IOS-SETTINGS | -- |
| Clear credentials | IOS-SETTINGS | -- |

---

## Unused / Inactive iOS Views

These Swift files exist in the codebase but are **not referenced** from any active navigation flow. They are earlier implementations superseded by newer views.

| File | Original Purpose | Replaced By |
|---|---|---|
| `SetupView.swift` | Koofr credential setup (email/password form) | Credentials now auto-fetched from frame via `fetchAndStoreCloudCredentials()` |
| `UploadView.swift` | Original upload screen (nav-bar based) | `UploadSheetView.swift` (IOS-UPLOAD) |
| `AddDestinationView.swift` | Add Koofr upload destination with folder browser | `AddSourceView` in `DestinationsView.swift` (IOS-ADDSRC) |
| `FileBrowserView.swift` | Browse files in a Koofr destination (with delete) | Not directly replaced; file management not in current scope |
