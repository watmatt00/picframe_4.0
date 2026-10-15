# Hardware test: WiFi setup mode + frame fixes (tkframe)

**Covers:** PL-062 (setup-mode fixes from `27ef223`), plus on-device checks for PL-063, PL-128 and PL-060.
**Frame:** tkframe, on `dev` at or after `6bb007e`.
**Who:** Matt runs every step. Claude only reads logs and state through the read-only `tkframe` SSH alias.
**Rule:** no commands that change the Pi. Everything below is done through the app, the router, a phone, or the power switch.

Mark each step `- [x]`, and add `<!-- FAIL: ... -->` notes for failures.

---

## 0. Before you start

- [ ] tkframe is on the latest `dev`: Manager app → frame → Software Update → Check, then Apply.
- [ ] Power-cycle tkframe once (unplug, wait 10 s, plug in). The watchdog only runs its boot checks at boot.
- [ ] Phone with **nRF Connect** (free, App Store) installed, for round B.
- [ ] Know how to block tkframe's WiFi client in the router app. Find tkframe by name or by its MAC address.

## 1. PL-063: Koofr flag corrects itself at boot

After the power cycle in step 0, Claude checks (read-only):
- [ ] `state.yaml` shows `koofr_configured: true`
- [ ] Watchdog log shows "koofr_configured=false but Koofr is configured — correcting flag" (first boot only), and no "generating setup instruction image".

## How setup mode starts here

Without SSH, the only way into setup mode is a real outage. The watchdog sets a flag after **10 min** without WiFi, and setup mode starts on the **next boot** (after a 90 s wait for WiFi). The router block must **disconnect tkframe from WiFi** (deauthenticate it, or deny it). A block that only pauses internet access is not enough: the watchdog checks whether WiFi is connected (`iw dev wlan0 link`), not whether the internet works.

BLE and the portal clear the flag and reboot as soon as they save credentials, so the recovery test (round A) and the BLE test (round B) each need their own outage. Allow about 30 min per round.

## 2. Round A: outage → setup mode → automatic recovery (PL-062)

- [ ] Block tkframe in the router. Note the time. The router shows tkframe disconnected, not just "paused".
- [ ] Wait 11 min. (Claude can confirm the flag: `needs_setup: true`, `setup_mode_reason: extended_outage`.)
- [ ] With tkframe **still blocked**, power-cycle it.
- [ ] About 2 min after boot, the slideshow is stopped and the setup AP **PicFrame-tkframe** is visible from your phone.
- [ ] Optional portal check: join PicFrame-tkframe; the portal page opens (or browse to `http://192.168.4.1`) and shows the WiFi form. **Don't submit**, because that reboots and ends this round.
- [ ] Unblock tkframe in the router. Note the time.
- [ ] Within about 15 min (plus 90 s), the setup AP disappears, the slideshow returns, and the Manager app shows the frame online.

Claude checks afterwards (`/var/log/picframe-watchdog.log`): outage countdown, "needs_setup flag set", boot into setup mode, then "Home WiFi available — left setup mode" and `needs_setup: false`.

## 3. Round B: BLE setup path (PL-062)

- [ ] Block tkframe, wait 11 min, power-cycle while still blocked, and confirm setup mode (PicFrame-tkframe visible), as in round A.
- [ ] **Unblock** tkframe in the router now, so it can connect once BLE saves the credentials.
- [ ] Right away, before the 15-min automatic retry: nRF Connect → Scan → **PicFrame-tkframe** (service `4fafc201-1fb5-459e-8fcc-c5c9c331914b`) → Connect.
- [ ] Characteristic `beb5483e-36e1-4688-b7f5-ea07361b26a8` → Write → type **Text (UTF-8)**:
  `{"ssid":"<your home SSID>","password":"<your WiFi password>"}`
- [ ] The frame reboots within a few seconds and comes back online with the slideshow (Manager app shows it online).

Claude checks afterwards: `/var/log/picframe-ble-setup.log` shows "BLE: received credentials for SSID '…'" and "WiFi configured. Stopping AP service and rebooting…"; the watchdog log shows a normal boot.

## 4. PL-128: Funnel URL in a browser

- [ ] Phone on **cellular** (WiFi off) → Safari → `https://tkframe.whale-ayu.ts.net` → a "PicFrame" page saying the dashboard is only available on its home network. Not raw JSON.

Claude checks from the PC: `curl -H 'Accept: application/json'` to the same URL still returns the JSON 403.

## 5. PL-060: uploads (Contributor app on the simulator)

- [ ] Upload a normal photo to tkframe from the Contributor app: succeeds and appears after sync.
- [ ] Upload the same photo again: "Already in … Not uploaded again." (PL-129 still works)
- [ ] Upload a large photo (20–40 MB if you have one): succeeds.

Claude checks from the PC: a 60 MB POST to `/api/v1/contributor/upload/…` gets 413 immediately; `free -m` on tkframe shows no lasting memory growth; the API log shows "Temporary files in /home/pi/picframe_data/tmp".

---

## Not covered here

- **PL-064** (state.yaml missing → no portal): testing it on hardware means deleting `/var/lib/picframe/state.yaml`, which would be a change on the Pi. Unit tests cover it (`tests/unit/test_setup_mode.py::TestMissingStateFile`). Confirm on the next real frame rebuild.

## Results

| Step | Result | Notes |
|---|---|---|
| 1 PL-063 | | |
| 2 Round A: outage → setup → recovery (+ portal) | | |
| 3 Round B: BLE | | |
| 4 PL-128 | | |
| 5 PL-060 | | |
