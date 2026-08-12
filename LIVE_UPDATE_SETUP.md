# Live Update Channel Setup

Questlog TL Farm Planner v21.9 can update itself from a public GitHub Releases repository.

## One-time setup

1. Create or choose a **public** GitHub repository for planner update releases.
2. In the planner, open **Settings -> Updates**.
3. Enter the repository as `OWNER/REPOSITORY`.
4. Save Settings.
5. Press **Check Now**.

No GitHub token is stored in the planner.

## Publishing a planner update

For each future version:

1. Create a GitHub Release with a version tag such as `v22.0`.
2. Attach the update ZIP produced for that version.
3. The asset may use either:
   - `Questlog_TL_Farm_Planner_UPDATE.zip`
   - the normal versioned file name, e.g. `Questlog_TL_Farm_Planner_UPDATE_v22_0.zip`
4. Publish the release.

The planner reads GitHub's latest public Release, finds the recognized ZIP, and requires
GitHub's SHA-256 asset digest before enabling live installation.

## App behavior

- Check for Updates may happen automatically on startup.
- Installation is always manual.
- Downloaded ZIPs are SHA-256 verified.
- Existing files are backed up before replacement.
- The local server restarts automatically.
- The already-open browser tab reconnects/reloads.
- Manual ZIP updates and ROLLBACK_LAST_UPDATE.bat remain available as fallback.
