# Pi Code-Modification Enforcement Options

**Created:** 2026-05-09  
**Status:** Implemented 2026-10-07 (PL-006) — see "Implementation" at the end.

## Problem

"Don't make code changes directly on the Pi" is currently policy-only (CLAUDE.md + memory). Goal: make it a technical barrier that's hard to accidentally violate.

## Current State

- Pi frames auth to GitHub via SSH key (`git@github.com:watmatt00/picframe_4.0.git`)
- Dev machine SSH key is hardcoded into `scripts/setup/install.sh` (lines 317-330) and added to Pi's `~/.ssh/authorized_keys` during install
- Claude currently has full shell access via SSH — can edit any file, run any command
- No `git push` workflow exists from the Pi, but it's not technically blocked

## Attack Vectors for Direct Pi Code Modification

1. SSH shell → direct file edit (`nano`, `sed`, `cp`, etc.) — unrestricted today
2. SSH shell → `git commit` / `git push` — unrestricted today
3. `git pull` from remote (via dashboard "Apply Updates") — already pull-only by design, low risk

---

## Options

### Option A — Read-only GitHub PAT (original idea)

Replace the SSH-based git remote on the Pi with HTTPS + a fine-grained GitHub PAT scoped to `contents: read` only.

```bash
# On Pi
git remote set-url origin https://x-access-token:<READ_ONLY_PAT>@github.com/watmatt00/picframe_4.0.git
git config credential.helper store
```

- **Blocks:** `git push` from Pi
- **Does NOT block:** Direct file edits via SSH, `git commit`
- **Verdict:** Partial — stops accidental push but the real risk is direct file edits, which this doesn't touch.

---

### Option B — Read-only GitHub Deploy Key

Register a second SSH key in GitHub repo settings as a **read-only deploy key** (GitHub supports this natively). Use this key on the Pi for git operations instead of a personal key.

- **Blocks:** `git push` from Pi (GitHub-level enforcement)
- **Does NOT block:** Direct file edits via SSH
- **Verdict:** Same limitation as A, but cleaner (no PAT rotation). Worth doing as hygiene regardless.

---

### Option C — Restricted SSH command in authorized_keys ← Recommended

Add a **second SSH key** specifically for Claude's inspection work. In `~/.ssh/authorized_keys`, prefix only that key with a `command=` directive pointing to an allowlist script. The user's own SSH key remains unrestricted.

**authorized_keys entry for Claude's key:**
```
command="/home/pi/bin/picframe-inspect",no-port-forwarding,no-X11-forwarding,no-agent-forwarding ssh-ed25519 AAAA... claude-inspect-key
```

**`/home/pi/bin/picframe-inspect` allowlist script:**
```bash
#!/bin/bash
case "$SSH_ORIGINAL_COMMAND" in
  "cat "* | "tail "* | "head "* | "ls "* | "journalctl "* \
  | "git log"* | "git status"* | "git diff"* \
  | "systemctl status "* | "ps "* | "df "* | "free"*)
    exec bash -c "$SSH_ORIGINAL_COMMAND"
    ;;
  *)
    echo "Command not permitted: $SSH_ORIGINAL_COMMAND" >&2
    exit 1
    ;;
esac
```

- **Blocks:** Any SSH command not on the allowlist — file edits, `git commit`/`git push`, script execution, pip install
- **Does NOT block:** Reading files and logs (intentional — inspection is useful)
- **Verdict:** Strong, targeted, zero friction change to user's own SSH workflow.

**Implementation steps:**
1. Generate a new SSH key pair: `ssh-keygen -t ed25519 -C "claude-inspect" -f ~/.ssh/id_claude_inspect -N ""`
2. Add public key to each Pi's `authorized_keys` with `command=` restriction
3. Create the `picframe-inspect` allowlist script on each Pi (`chmod +x`, owned by pi)
4. Update `install.sh` to optionally install the restricted key and script during setup
5. Keep existing dev SSH key unrestricted for user's own sessions

---

### Option D — Dedicated read-only Pi user

Create a `picframe-ro` system user on the Pi with read access to project files and logs. Claude SSHes as `picframe-ro`, not `pi`.

- **Blocks:** Writes to project directory (filesystem-enforced by user permissions)
- **Does NOT block:** Can still read everything; still an SSH session
- **Verdict:** Effective but heavier — requires setup on 3 frames, must be added to `install.sh`.

---

### Option E — Remove Claude SSH access entirely (hardest barrier)

Delete the dev SSH key from Pi `authorized_keys`. Claude cannot SSH at all.

For log inspection: use the dashboard log viewer (already exists in Settings tab) or user manually SSHes and pastes output.

- **Blocks:** All SSH-based code modification — absolute enforcement
- **Does NOT block:** Claude instructing the user to run harmful commands (policy still needed)
- **Verdict:** Maximum enforcement. Loses some convenience for log inspection. Dashboard log viewer handles ~80% of log needs.

---

## Recommendation

**Option C + Option B together:**

- **Read-only deploy key (B):** Pi cannot push to GitHub — GitHub-level enforcement, independent of SSH
- **Restricted SSH key (C):** Claude can inspect logs/git status/service health, but cannot modify anything
- **User's own SSH key:** Unchanged, fully unrestricted — zero friction to normal dev workflow

This gives Claude meaningful inspection capability while making code modification technically impossible rather than just policy-prohibited. All three Pi frames need the one-time key + script setup; new installs get it via `install.sh`.

## Files to Modify When Implementing

| File | Change |
|------|--------|
| `scripts/setup/install.sh` | Add restricted key to authorized_keys, install allowlist script |
| Each Pi's `~/.ssh/authorized_keys` | Add restricted key entry (one-time manual) |
| Each Pi's `/home/pi/bin/picframe-inspect` | Create allowlist script (one-time manual) |
| GitHub repo Settings → Deploy Keys | Add read-only deploy key (web UI, no code change) |

---

## Implementation (2026-10-07, PL-006)

Findings that changed the plan:
- `picframe_4.0` is a **public** repo and frames pull it anonymously over HTTPS (`install.sh` `REPO_URL`). No GitHub key is needed on a Pi, so Option B (deploy key) is unnecessary: the fix is to delete the three account-wide GitHub keys. `update_app.sh` Step 0 switches any leftover SSH remote to HTTPS first.
- The Option C example script above is **unsafe**: `bash -c` with prefix matching lets `cat x; rm -rf ~` through. Not used.

What was built:
- `scripts/pi/picframe-inspect` — Python command filter. Splits `SSH_ORIGINAL_COMMAND` with `shlex`, rejects shell metacharacters, checks a per-command allowlist (git read subcommands only, systemctl read verbs only, exact tailscale invocations, etc.) and `execvpe`s with a clean env and pagers disabled. Never runs a shell. Tests: `tests/unit/test_picframe_inspect.py`.
- `scripts/setup/install_inspect_key.sh` — run by the user on the Pi. Installs the filter to `~/.local/bin/picframe-inspect` and adds `restrict,command="..."` + `scripts/setup/claude_inspect.pub` to `authorized_keys` (atomic, flock'd, idempotent). `--remove-dev-keys` removes the unrestricted dev PC keys (by fingerprint) and refuses if sshd has password login disabled.
- `install.sh` installs the inspect key instead of the unrestricted dev key on new frames.
- The filter copy in `~/.local/bin` only changes when the user re-runs the install script, so a pushed change to the allowlist cannot widen access on its own.

Limit: Claude runs as the same Unix user as the developer on the PC. The restriction becomes real only once `--remove-dev-keys` has run, because until then the unrestricted PC keys still open the Pi.

Status on tkframe (2026-10-07): inspect key installed and verified (allowed reads work; writes, chained commands, git writes and shells refused). The dev keys are **still installed**: tkframe's sshd is key-only (`sshd_config.d/50-cloud-init.conf`, Raspberry Pi Imager "public-key only"), so removing them needs a passphrase-protected full-access key for the user first. `--remove-dev-keys` now checks sshd live and refuses if it would lock the user out.
