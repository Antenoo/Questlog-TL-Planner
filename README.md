# Questlog-TL-Planner

Update releases for my local Questlog Throne and Liberty Farm Planner.

## Questlog TL Farm Planner — Local Web App

This is the first web-app version of the Questlog farming/exporter project.

## Why this exists

The command-line exporter reached a point where the main problem was no longer
"can Questlog be scraped?" but "how do we make this painless to use repeatedly?"

This app wraps the scraper in a local browser UI.

## First-time setup

1. Extract the ZIP.
2. Run `SETUP_FIRST_TIME.bat`.
3. Wait for `SETUP COMPLETE`.

You only need to do that once.

## Normal use

Run:

`START_APP.bat`

It starts the local server and opens:

`http://127.0.0.1:8765`

There is no hosting or external account involved. The app runs entirely on your PC.

## v16 fixes included

### 1. Recipe URL identity bug fixed

These are now considered the same item:

- `/db/item/gauntlet_aa_S1_arch_001?level=`
- `/db/item/gauntlet_aa_S1_arch_001`
- `/db/item/gauntlet_aa_S1_arch_001?level=85`

Query parameters are ignored for DB-record identity.

This restores real `Craftable From` routes.

### 2. Direction-aware recipes

If the current item appears in the recipe Result cell:
- `Craftable From`

If the current item appears in Materials:
- `Used By Recipes`

Only the former is treated as an acquisition route.

### 3. Container contents + probability

Tables shaped:

`Name | Quantity | Drop Type | Probability`

are classified as `Container Contents`.

This lets the app display probabilities such as a specific gear piece having a
3.125% chance inside a reward chest.

### 4. Local disk cache

Questlog item pages are cached under:

`data\cache`

Default cache lifetime: 7 days.

Repeated scans can therefore reuse already-read Questlog DB pages.

Use the app's `Force refresh cached pages` checkbox when you want fresh data.

### 5. Controlled recursion

Only material/container item links deepen the graph.

Direct NPC/resource/dungeon evidence stays terminal.

Default expansion depth: 2.

## UI

The first version contains:

- Build URL field
- Scan / Update Build button
- Chromium visible/hidden toggle
- Force refresh toggle
- Recursive-depth selector
- Progress status
- Farm Plan view
- Container Contents view
- Raw JSON view
- JSON export download
- Clear Cache button

Your build URL is remembered by the browser through localStorage.

## Local build URL

Set your own Questlog character-builder URL in the planner. The value is stored in
local configuration and must not be committed or included in release packages.

## Important limitation

Questlog package/container pages often tell us what is inside the package, but not
always how that package itself is awarded. Those pages are still useful because the
app preserves the content/probability data. Future versions can add more specific
source-type handlers when we identify additional Questlog structures.


## v17.1 hotfix

Fixes an export error where `data\exports` could be missing after extracting the ZIP.
Empty folders are not always preserved inside ZIP archives. The app now creates both
`data\cache` and `data\exports` automatically at startup.


## v17.2 — Diagnostic Bundle

A new **Download Diagnostic Bundle** button creates one ZIP that is meant to be
uploaded back into ChatGPT when something breaks or when the farm data looks wrong.

The bundle contains:

- `support_meta.json`
- `config.json`
- `cache_stats.json`
- `job_status.json` when a scan exists
- the selected/latest scan JSON export
- `logs/app.log`

It intentionally does **not** include the full page cache, so the support bundle stays
small and easy to upload.

### How to use it for updates

1. Reproduce the problem or complete a scan.
2. Click **Download Diagnostic Bundle**.
3. Upload that ZIP into the chat and describe what looked wrong.

That should usually be enough to diagnose the next update without asking you to hunt
for individual files.


## v17.3 — Collapsible Farm Plan + Questlog Icons

Farm Plan item slots are now collapsed by default.

Each equipped item is shown as a compact header. Click the header to open or close it.
There are also **Expand All Slots** and **Collapse All Slots** buttons.

The scraper now captures the equipped item's image URL directly from the Questlog
character-builder equipment grid and stores it as `item_icon_url` in the scan export.
The web UI displays that Questlog-hosted image beside each item when available.

This does not download or redistribute an icon pack; the local browser simply displays
the image URL Questlog already exposes for the equipped item.


## v18 — Planner UI / Cancellation Release

### Safe scan cancellation
The app now includes **Cancel Scan**.

Cancellation is cooperative rather than force-killing Python. The scraper checks for
the request between equipment slots, page loads, scroll steps, graph nodes, and crawl
delays. Chromium is then closed in a `finally` cleanup block and the web app remains
running.

### Headless by default
**Show Chromium while scanning** is now OFF by default. Turn it back on when debugging.

### Live scanner status
During a scan the app shows:
- scanner state
- current equipment item
- pages requested
- cache hits
- downloaded pages

### Questlog-inspired equipment cards
Each equipped item is a collapsed card with:
- larger Questlog item icon
- item name
- compact acquisition-type badges
- Questlog DB link
- cleaner Direct Drop / Crafting / Dungeon / Container sections
- a separately collapsed expanded-material/source graph

The design is inspired by the information hierarchy of Questlog's item database pages
without attempting to copy their site pixel-for-pixel.


## v18.1 — Crafting Material Name / Icon Fix

Questlog's recipe table frequently uses the **quantity** as the clickable anchor text
for a material. That meant the UI could display entries like `80 ×80`, `20 ×20`,
and `12 ×12` instead of the actual material names.

v18.1 resolves each recipe-material URL against the already-expanded item graph and
uses the material page title as the display name.

Example:

- `Adventure Token T3 — Required: ×80`
- `Precious Crystal — Required: ×20`
- the relevant main crafting material — `Required: ×12`

The scraper also records a best-effort `icon_url` for expanded DB item pages using
Questlog's item-page image metadata / item imagery, allowing material icons to appear
beside crafting requirements after a fresh v18.1 scan.

If Questlog does not expose an icon for a specific page, the material name and quantity
still display correctly with an empty icon placeholder.


## v18.2 — Live status, timer, hover previews, and in-place updater

### Fixed live scanner statistics
Previous progress events replaced the entire progress object. A small event such as
"Opening URL" therefore erased `current_item` and page counters, making the UI appear
stuck at Running / 0 / 0 / 0.

Progress updates are now merged. The current item and page statistics persist correctly.

### Scan timer
A live elapsed timer runs while a scan is active and freezes at the final duration when
the scan finishes, errors, or is cancelled.

### Item hover preview
Hover over an equipped item card for a Questlog-inspired quick preview containing:
- larger item icon
- acquisition badges
- available base DB stats
- skill-core/perk names when available
- a short crafting-material snapshot

The existing collapsed Farm Plan cards/tabs remain the source for full details.

### In-place updates
This release introduces:
- `APPLY_UPDATE.bat`
- `ROLLBACK_LAST_UPDATE.bat`
- `update_manager.py`

Future update ZIPs can be extracted directly into the same permanent app folder.
Run `APPLY_UPDATE.bat`; changed files are backed up automatically under
`data\\update_backups`. Cache, exports, config data, and `.venv` are preserved.


## v18.2.1 — Headless build-grid hotfix

The first v18.2 headless run could fail with `Equipment grid not found` before any DB
pages were scanned. The diagnostic bundle showed exactly that: the build-discovery
phase failed while page counters were still zero.

Questlog's character-builder can finish `DOMContentLoaded` before its equipment
component has hydrated. v18.2.1 now:
- waits up to 15 seconds for the equipment grid while re-checking the Equipment tab
- gently nudges client/lazy rendering
- performs one controlled page reload if the first hydration fails
- waits another 12 seconds after the reload
- includes the page title and a short visible-text sample in the error if it still fails

No cache needs to be cleared for this update.


## v18.2.2 — Cloudflare / headless-mode adjustment

The v18.2.1 diagnostic confirmed that Questlog's Cloudflare protection is blocking the
Playwright session specifically when Chromium is run headless.

The app does not attempt to bypass or evade Questlog's security controls.

Changes:
- **Show Chromium while scanning** is ON by default again.
- The UI marks visible Chromium as the recommended mode.
- Cloudflare's `Attention Required / Sorry, you have been blocked` page is detected
  immediately.
- A blocked headless run stops immediately with a useful message instead of spending
  ~30 seconds waiting/reloading for an equipment grid that cannot appear.
- The app does not retry or attempt to work around the Cloudflare block.

The live status/timer changes from v18.2 remain intact.


## v18.2.3 — Icon-only hover preview

The Questlog-style quick preview now opens only while the mouse is over the equipped
item's icon.

Hovering the item name, acquisition badges, Questlog DB link, expanded Farm Plan
content, or the rest of the slot card no longer opens the preview.


## v18.2.4 — Strict icon-only hover + frontend cache fix

The diagnostic bundle confirms the backend was already v18.2.3, but the browser could
still retain an older copy of the inline frontend from `/`.

This release disables browser caching for the main `index.html`, so future UI patches
are picked up after restarting/reloading the app.

The preview trigger was also rewritten:
- only the top-left equipped-item image receives `data-item-preview="true"`
- one delegated pointer handler checks the element physically under the mouse
- moving anywhere outside that exact icon immediately hides the preview
- item names, badges, links, card backgrounds, and expanded details cannot trigger it

No new scan or cache clear is required.


## v19.0 — Planner release

The app now moves beyond raw scraped tables and acts more like a build/farming companion.

### Build Overview
A compact 15-slot equipment overview is shown above the tabs. Each slot has:
- the Questlog icon
- item name and equipment-slot label
- a persistent progress status: Not started / Farming / Ready / Complete
- an Open button that jumps directly to that item's detailed Farm Plan card

Progress is stored locally in the browser and survives app restarts.

### Farm Dashboard
A new default **Farm Dashboard** answers "what can I go do?" rather than only
"what does this item contain?"

It aggregates:
- boss / NPC sources
- dungeon sources
- reward / chest sources
- shared crafting materials across equipped-item recipes
- the equipped targets helped by each activity/material

Questlog probability values remain evidence only and are not treated as guaranteed
player-eligible odds.

### Cleaner Farm Plan
Visually identical Questlog source rows are presentation-deduplicated. Raw JSON still
retains the individual database records.

### Better quick previews
Icon-only hover previews now also work from the Build Overview and Dashboard target
icons, and include:
- progress status
- source highlights
- acquisition types
- DB stats when Questlog exposes a Base Stats table
- skill-core/perk data when available
- crafting snapshot

### Load Last Scan
A new **Load Last Scan** button opens the latest successful JSON export from disk
without scraping Questlog again. This is useful for normal day-to-day use and reduces
unnecessary work on older PCs.


## v19.1 — Progress-aware material inventory

### Roomier Build Overview
The equipment grid now uses wider cards with larger icons, more padding, and a higher
minimum card width so item names/status controls are less cramped.

### Completed items now reduce material requirements
Shared Crafting Materials only totals recipes for equipment that is not marked Complete.
Changing a Build Overview item to Complete immediately recalculates the dashboard.

### Track materials you already own
Each material now shows:
- Required
- Owned (editable input)
- Remaining

Owned quantities are stored in browser localStorage for the current Questlog build URL
and survive app restarts. Remaining is calculated as `max(Required - Owned, 0)`.

No rescan is required for these UI/planning changes.


## v19.2 — Automatic last-scan restore

Previously, each browser tab started with `currentData = null`. The scan export was
still safely stored under `data\exports`, and browser localStorage still retained item
statuses/material inventory, but the frontend did not automatically reload the saved
scan. That made app restarts and updates *look* as if another Questlog scan was needed.

v19.2 automatically loads the newest successful `farm_scan_*.json` export when the app
page opens.

Result:
- restarting `START_APP.bat` restores the previous build automatically
- opening a new browser tab restores the previous build automatically
- applying an app update no longer requires another Questlog scrape just to see the
  same build again
- item progress statuses and owned-material amounts continue to come from persistent
  browser localStorage
- **Load Last Scan** remains available as a manual recovery button

A fresh Questlog scan is only needed when you actually want updated build/database
information.


## v19.3 — Completed gear drawers + Sollant crafting budget

### Completed gear is moved out of the way
Both Build Overview and Farm Plan now split equipment into:
- unfinished gear shown normally
- a collapsed **Completed Gear** drawer

Changing an item's status immediately moves it between those sections. Opening a
completed item from Build Overview automatically opens the completed Farm Plan drawer.

The "What can I go do?" dashboard also ignores completed gear now.

### Sollant crafting budget
Questlog recipe pages expose a **Gold Cost** alongside ingredients. v19.3 captures
that value for the primary non-core equipment recipe during a normal scan.

The Farm Dashboard adds:
- outstanding known crafting Sollant
- editable current Sollant wallet
- remaining Sollant needed
- per-item crafting costs for unfinished craftable gear

Your current Sollant amount is stored locally per build URL.

### One scan required for the new cost data
Older saved scans do not contain `crafting_recipes[].sollant_cost`. The app continues
to auto-load them normally, but it will label those craft costs as not captured.
Run **one** fresh Scan / Update Build after installing v19.3 to populate automatic
Questlog crafting costs. Future app restarts/updates still auto-load the saved scan.


## v19.4 — Daily Archboss priority planner

A new **Boss Priority** tab helps answer:
> "I haven't used my Archboss participation reward today. Which boss should I pick?"

### Daily participation state
The planner stores:
- whether the day's participation reward is still Available or already Used
- which boss consumed it
- today's marked Archboss kills
- whether Guild-event rewards are actually eligible for the player

Guild events are excluded from recommendations when Guild reward eligibility is off.

### Upcoming-event planner
Add the Archbosses available today with:
- local event time
- boss name
- Peace / Guild event type
- available/unavailable toggle

The planner ranks the events and can explicitly recommend **waiting for a later boss**
when spending the participation opportunity on an earlier, lower-value boss would be
worse for the configured goals.

### Two-part boss value
Bosses use a priority profile with:
- repeat/direct-drop value
- an extra participation-reward value when the daily participation is still unused

This is important because a boss can be the best first kill of the day but a worse
repeat target after participation has already been spent.

Seeded profiles:
- Deluzhnoa — Primary progression target
- Ramux — Strong direct upgrade
- Tevent — Backup target

All profiles are editable in the UI.

### Data provenance
Schedule and participation rules are editable planner assumptions. They are not
presented as Questlog or official-system data.


## v19.6 — Archboss weekly schedule templates

This release combines the refined Archboss loot model with editable recurring schedule
templates. Player-specific dates and selections remain in ignored local planner state.

### Correct Ascended pool
The recurring purple pool is now:
1. Ascended Giant Cordy
2. Ascended Deluzhnoa
3. Ascended Queen Bellandir
4. Ascended Tevent

Ramux remains the separate Nix Archboss.

### Observed weekly structure
The template generator uses:
- Tuesday / Friday: the four-boss Ascended pool at 19:00 and 22:00
- Wednesday / Saturday: Ramux at 19:00 and 22:00, with the four-boss Ascended pool
  added to one of the two slots
- Sunday / Monday / Thursday: no recurring Archboss template observed

The Wed/Sat mixed slot is not guessed or seeded from private observations. The user
chooses 19:00 or 22:00 locally when generating that template.

### Peace / Guild remains live-schedule data
Generated events start as `Set Peace/Guild…`.

This is deliberate because Peace/Guild status varies boss-by-boss inside a time slot.
Unknown event types are excluded from recommendations until confirmed, preventing an
ineligible Guild event from being recommended accidentally.

### Local priorities
Source code does not seed player-specific boss priorities. Each installation stores its
own selections in ignored planner state.

### Two-stage daily route
The Boss Priority tab can now give a simple two-step plan:
- where to spend the first/full-eligibility Archboss opportunity
- which later boss is best for basic direct-drop/shard RNG after that

The scoring model remains:
- first eligible Archboss: Direct RNG + Participation + Contribution
- later kills: Direct RNG only

Schedule and loot-eligibility rules are editable planner assumptions, not official or
Questlog data.


## v19.6.1 — Force 24-hour Archboss time entry

The Boss Priority event editor no longer relies on the browser's native `type="time"`
control, because some browsers render that control using a 12-hour AM/PM picker even
when the planner stores 24-hour values.

Archboss event times now use a strict text-based `HH:MM` field:
- `19:00`
- `22:00`
- `07:30`

Convenience input is supported:
- typing `1900` normalizes to `19:00`
- typing `900` normalizes to `09:00`

Invalid values are rejected. The schedule template itself continues to use 19:00 and
22:00 as before.


## v19.6.2 — Schedule preview is independent from the real day

The Archboss planner previously reused `dayKey` for both:
- today's participation/full-eligibility ledger
- the schedule date being previewed

That caused an intentionally selected Tuesday/Friday/future date to be reset back to the
computer's real calendar day.

The two concepts are now separated.

### Real day
Tracks:
- whether today's full eligibility has been used
- which boss consumed it
- today's marked kills

This still resets automatically when the computer's local calendar day changes.

### Schedule preview date
Can now be changed freely to any supported date without changing the real-day ledger.

When the preview date is not today:
- the UI clearly shows **Preview mode**
- recommendations assume that planner day begins with full eligibility
- Mark killed is disabled
- the "used/available today" button is disabled
- changing/generating a preview never overwrites today's participation history

This means the user can test Tuesday, Friday, Wednesday, Saturday, future dates, or
historical supplied schedule dates without changing the Windows clock.


## v19.6.3 — Reversible Archboss kill tracking

Archboss kills are no longer one-way.

After marking an event killed, the same button becomes **Undo kill**. This is useful
when the wrong boss was clicked accidentally.

When a kill is undone, the planner rebuilds the day's kill ledger from the events still
marked killed:

- if no killed events remain, full eligibility returns to **Available**
- if another killed event remains, the earliest marked event becomes the recorded boss
  that consumed the first/full-eligibility opportunity
- Today's marked-kill history is rebuilt automatically

Preview mode remains read-only, so future/past schedule testing cannot modify today's
kill state.


## v19.6.4 — Context-aware weekly schedule controls

The **Wed/Sat Ascended-pool slot** selector was previously visible on every date,
including Tuesday and Friday. That was confusing even though the generator itself
already understood the different weekday templates.

The schedule UI now changes with the selected date:

### Tuesday / Friday
- shows only the schedule date
- hides the Wed/Sat mixed-slot selector entirely
- button reads **Generate Ascended Pool**
- explains that the four-boss Ascended pool is present at both 19:00 and 22:00

### Wednesday / Saturday
- shows the mixed 19:00 / 22:00 Ascended-pool selector
- button reads **Generate Ramux / Mixed Events**
- mixed-slot time is selected locally and no private dates are pre-filled

### Sunday / Monday / Thursday
- mixed-slot selector is hidden
- generation button is disabled and reads **No Recurring Template**

This is a UI clarification only; the underlying weekly schedule rules are unchanged.


## v20.0 — Today dashboard, craft readiness, and portable backups

### Today dashboard
The Farm Dashboard now starts with a compact **Today** summary:
- today's Archboss recommendation when today's Boss Priority schedule is configured
- the best later direct-RNG boss after the first/full-eligibility kill
- closest / individually ready crafts
- remaining known Sollant crafting budget

A future/past Boss Priority preview is never mistaken for today's recommendation.

### Craft Readiness
Each unfinished craftable item is checked against:
- saved owned-material quantities
- Questlog recipe requirements
- saved current Sollant
- captured Questlog crafting Gold Cost / Sollant

States include:
- Ready to craft individually
- Almost ready
- Blocked / material shortfalls
- Materials ready but Sollant cost unknown

Important: readiness is currently per-item. Shared materials are not reserved between
multiple simultaneous crafts yet, so two items can both appear individually ready if
the same inventory stack could satisfy either one.

### Export / Restore Planner Backup
New toolbar buttons:
- **Export Planner Backup**
- **Restore Planner Backup**

The backup JSON contains:
- item progress statuses
- material inventory
- Sollant wallet
- Boss Priority state
- build URL / depth preferences
- the currently loaded scan snapshot

This means the planner can be moved or recovered even if browser localStorage is lost.

### Offline restored scan fallback
Restored backups save the embedded scan snapshot locally. If `data\exports` is missing
on a future/reinstalled copy, the frontend can fall back to the restored scan without
immediately requiring a Questlog scrape.

This makes the local app substantially more independent from ChatGPT and from one
browser session.


## v20.0.1 — Dashboard / tab rendering hotfix

v20.0 introduced the Today dashboard as a child of `#viewDashboard`, but
`renderDashboard()` then replaced the entire `#viewDashboard.innerHTML`.

That deleted the `#todayDashboard` element. The next call to `renderTodayDashboard()`
therefore threw a JavaScript error. Because `renderAll()` stopped at that exception,
Boss Priority, Farm Plan, Container Contents, and Raw JSON were never rendered, so
clicking those tabs appeared to show a blank page.

Fixes:
- `#todayDashboard` is now a permanent host.
- normal Farm Dashboard content renders into a separate `#dashboardBody`.
- each major tab/view is rendered through an independent safety wrapper, so one future
  UI rendering bug cannot prevent the other tabs from loading.
- Today rendering now safely checks that its host exists.

No scan/cache changes are required.


## v20.1 — Container Contents polish

The Container Contents tab has been redesigned to reduce visual clutter while preserving
the underlying Questlog evidence.

- Containers are collapsed by default.
- Headers show DB-row count, non-currency drop count, under-1% count, and rarest chance.
- Non-currency drops use compact cards with icons and are sorted rarest first.
- Repeated Sollant rows are grouped into one compact "Sollant rolls" section.
- Exact possible Sollant amounts are still shown.
- Added search, "Only drops under 1%", Expand All, and Collapse All.
- No Questlog rescan is required.


## v20.2 — Container drop icons + linked icons

Questlog container tables already display item icons, but older scraper exports only
stored each image's `alt` text. As a result, many Container Contents cards had an empty
icon even though the item name and DB URL were available.

### New scan metadata
The table parser now stores `image_srcs` for each linked item directly from Questlog's
table DOM.

### Selective legacy-cache refresh
A normal **Scan / Update Build** after v20.2 checks cached pages.

Only cached pages that:
- contain Container Contents data, and
- still lack the new linked image metadata

are reloaded from Questlog. Other cached pages remain cache hits.

This means **Force Refresh is not required** just to fill the missing icons.

### Clickable icons
Container drop icons now link to the same Questlog DB item page as the item name.

Even when an old scan has no icon yet, the placeholder itself is still a clickable DB
link so navigation remains useful.


## v20.3 — Priority-aware resource allocation + next-target ranking

### Item resource priorities
Every Build Overview item now has:
- High
- Normal
- Low

Priority is stored locally per build and is included in Planner Backup exports.

### Shared-material reservation
The planner now simulates resource reservations in:
`High → Normal → Low`

Within the same priority, items manually marked Ready/Farming are considered before
Not Started items.

Materials are deducted from a virtual free-inventory pool as they are reserved.
Sollant is reserved only once the item's full material bundle is reserved.

This prevents several crafts from simultaneously claiming the same shared material stack.

### Priority Resource Allocation
The old per-item Craft Readiness panel is now a priority-aware allocation panel showing:
- reserved quantity per material
- missing quantity after higher-priority reservations
- reserved / missing Sollant
- Ready / Close / Blocked state after allocation

These are planning reservations only; the user's entered inventory is never modified.

### Next Planner Targets
The Farm Dashboard and Today summary now rank unfinished target items.

Ranking is:
1. user-selected High / Normal / Low priority
2. actionability (craft now, direct drop/dungeon route, close craft, etc.)
3. manual progress state and route details

This is explicitly a planner ranking and does not claim to calculate actual in-game DPS
or item-power differences.

### Shared-material transparency
Shared Crafting Materials now show:
- how much is reserved by the priority allocator
- how much remains free after reservations

Changing any item priority immediately recalculates the dashboard.


## v20.4 — Single-tab restart / automatic update refresh

`launcher.py` previously called Python's `webbrowser.open()` every time
`START_APP.bat` launched the server. Browsers normally interpret that as "open another
tab", even when the planner is already open.

v20.4 changes the workflow:

1. `START_APP.bat` starts only the local server.
2. An already-open `http://127.0.0.1:8765` tab checks `/api/health` every few seconds.
3. If the server disappears during an update/restart, that SAME tab waits.
4. When the server returns, the existing tab reloads itself.
5. If a future update changes the backend version, the existing older frontend detects
   the version mismatch and reloads itself automatically.

A small status message appears while the local server is unavailable.

### If no tab is open
Run `OPEN_APP.bat`.

This is separate on purpose because a local Python process cannot reliably tell Opera,
Chrome, Edge, Firefox, etc. to refresh a specific existing tab without browser-specific
automation/extensions.

### First v20.4 update
The page that is already open before installing v20.4 does not yet contain the new
heartbeat JavaScript. Therefore, after applying v20.4, manually refresh the existing
planner tab once.

From that point onward, later app restarts and updates can reuse/refresh the same tab.

## v21.0 — App-owned state, Upgrade Queue, and scan change history

### Planner state now lives in the app folder
Important planner data is now stored in:

`data\planner_state.json`

This includes, per Questlog build:
- equipment progress/status
- High / Normal / Low priorities
- material inventory
- Sollant wallet
- Boss Priority state and schedule settings
- explicit Upgrade Queue order

Global planner preferences such as the last build URL and recursive depth are stored
there too.

On the first v21 startup, if `planner_state.json` is empty, the frontend migrates the
existing v20 browser localStorage values into the app-owned file automatically. The old
browser values are left untouched as a migration fallback, but new planner changes use
the app-owned state as the source of truth.

Writes use an atomic temporary-file replacement on the backend.

Planner Backup v2 now exports this app-owned state. Restore remains backward compatible
with older v20 backups that stored `local_storage` instead.

### Explicit Upgrade Queue
Build Overview now contains an Upgrade Queue for all unfinished gear.

- Move gear up/down with arrow buttons.
- Queue position is the exact order used for shared-material and Sollant planning.
- Marking an item Complete removes it from the queue.
- Making it unfinished again adds it back.
- **Reset from priorities** rebuilds the queue using High → Normal → Low and slot order.

High / Normal / Low still describes intent, but the explicit queue is authoritative for
resource reservations and Next Planner Targets.

### Scan History & Change Detection
A new **Scan History** tab records successful scans from v21 onward.

Every successful scan is compared with the previous saved scan for the same Questlog
build URL. The lightweight history records:
- equipment-slot changes
- equipped items whose Questlog acquisition/container/crafting evidence changed
- evidence rows added
- evidence rows removed

The complete scan JSON remains under `data\exports`; history metadata is stored in:

`data\scan_history.json`

Scan history and planner state are also included in future diagnostic bundles.

No fresh Questlog scan is required to install v21. A new scan is only needed when the
user wants to create a new change-history entry / compare current Questlog data.


## v21.1 — Automatic server restart after updates

The previous same-tab refresh feature was only half of the workflow:
the browser page correctly detected that the local server had stopped, but
`APPLY_UPDATE.bat` did not start the server again. The user still had to run
`START_APP.bat` manually.

That meant the existing tab could wait forever, and manually refreshing while
the server was down replaced the planner page with the browser's
`ERR_CONNECTION_REFUSED` page. Once that happens, the planner JavaScript is no
longer loaded, so it cannot auto-reconnect.

v21.1 fixes the update lifecycle:

1. Leave the existing planner browser tab open.
2. Close the running planner server window.
3. Extract the update into the permanent app folder.
4. Run `APPLY_UPDATE.bat`.
5. The updater applies the patch.
6. If the update succeeded, it automatically starts `START_APP.bat`.
7. The existing planner tab sees the server return and reloads itself.

Do not manually refresh the browser while the red "server is restarting"
message is visible. The tab will handle it automatically once the server is
back.

`OPEN_APP.bat` remains available if there is no planner tab open.


## v21.2 — Automatic System Health / post-update self-test

The planner now runs a non-destructive self-test automatically after startup.

Backend checks:
- backend/version
- config.json required settings
- data/ read/write
- planner_state.json read/schema
- planner-state temporary write round-trip
- latest farm scan validity
- scan-history validity
- cache directory
- update/start/open/rollback recovery files

Browser/UI checks:
- frontend version
- app-owned planner state loaded
- scan loaded in the browser
- Build Overview, Farm Dashboard, Boss Priority, Farm Plan, Container Contents,
  Scan History, and Raw JSON render successfully
- planner backup payload matches the v21 schema

A persistent green/amber/red health badge appears near the planner controls.
The new System Health tab shows every individual check and explanation.
Run Health Check reruns it manually.

Backend results are saved to data/health_report.json and included in diagnostic bundles.
Temporary write-test files are deleted immediately; the self-test never modifies actual
planner state.


## v21.3 — Target Gear / Upgrade Paths

The planner can now distinguish between:
- what is currently equipped
- what the player is actively trying to obtain

### Upgrade Paths tab
A new Upgrade Paths tab shows every equipped slot and its ordered target list.

Each target stores:
- item name
- optional Questlog DB URL
- Primary / Secondary / Backup role
- Planned / Farming / Obtained status
- optional planner note

Targets are stored in the app-owned `data/planner_state.json` and are therefore also
included automatically in Planner Backup exports.

### Questlog route awareness
When a target item already exists anywhere in the loaded scan graph, the planner resolves
the item automatically and shows:
- its Questlog icon
- a `Questlog scan` source badge
- the recognized acquisition action such as Direct Drop, Dungeon, Reward Source, or Craft

If the target is not present in the current graph, it remains a valid Manual Target.
This cleanly separates user-defined progression intent from Questlog-derived evidence.

The Add Target form uses the loaded scan graph as autocomplete. If an exact scanned item
name is selected, its Questlog URL is filled into planner data automatically.

### Build Overview integration
Every equipped gear card now shows its highest active target, plus a Path button that
jumps directly to that slot's Upgrade Path.

### Next Planner Targets integration
The Today dashboard and Farm Dashboard now prefer explicit Target Gear when any targets
exist:
1. Primary
2. Secondary
3. Backup

Targets marked Farming are surfaced ahead of other targets at the same role/order.

The old equipped-item Upgrade Queue remains intact and follows explicit target gear in
the planner ranking.

This makes the ranking reflect where the player is actually trying to go instead of
treating the currently equipped item as the final goal.

### Status behavior
`Obtained` targets remain in the upgrade path as history but are excluded from active
planner targets.

No Questlog scan is required to use manual targets. A scan only improves automatic route
and icon resolution when the target appears in the scan graph.


## v21.3.1 — Clean server-console shutdown hotfix

Previously `START_APP.bat` ran Python directly inside the batch file:

`call ".venv\Scripts\python.exe" launcher.py`

When Ctrl+C stopped uvicorn, Windows CMD also treated the interrupt as an interruption
of the surrounding batch job. This caused:

`Terminate batch job (Y/N)?`

After answering `Y`, the dedicated console could then remain sitting at a normal
`C:\...>` command prompt.

v21.3.1 changes `START_APP.bat` into a tiny launcher only. It starts a dedicated
`cmd /c` session which runs `python.exe launcher.py` directly, then the launcher batch
exits immediately.

Result:
- Ctrl+C still gives uvicorn its graceful shutdown.
- There is no active START_APP batch job in the server console.
- After uvicorn finishes, the dedicated `cmd /c` process exits.
- The server CMD window should close automatically instead of leaving a prompt behind.
- The update auto-restart workflow continues to use the same START_APP.bat entry point.

No Questlog data, planner state, scan cache, or build settings are changed.


## v21.4 — In-game Knowledge Routes

Questlog remains the primary scraped evidence source, but the planner now has a separate
persistent knowledge layer for progression mechanics Questlog does not expose cleanly.

### Source separation
The UI distinguishes three evidence types:
- **Questlog** — scraped/database evidence.
- **In-game confirmed** — manually recorded mechanics the player has verified in game.
- **Manual / needs verification** — useful planner information that should not yet be
  treated as confirmed.

Supplemental routes are never rewritten as Questlog evidence.

### App-owned knowledge file
Supplemental routes are stored in:

`data/user_knowledge/routes.json`

The file is created automatically on first v21.4 startup and is preserved by normal
updates.

### Empty-by-default knowledge store
New installations start with no seeded player knowledge. Routes are added locally and
remain in the ignored `data/user_knowledge/` directory; updates never publish or replace
them.

### Knowledge Routes tab
A new tab allows the player to:
- add a missing route
- edit or delete an existing route
- choose In-game confirmed vs Manual / needs verification
- enter target aliases
- enter route steps
- add per-step notes with `Step name :: note`
- attach a Questlog target URL when available
- keep an evidence/planner note

### Planner integration
Questlog still wins whenever it exposes an actionable acquisition route.

When Questlog does **not** expose an actionable route, the planner now checks the
supplemental knowledge file. This affects:
- Upgrade Paths
- Next Planner Targets
- Today recommendations
- equipped-item route summaries

This means a locally selected target can remain actionable even when an important
acquisition mechanic is missing from Questlog.

### Backup / diagnostics / health
Planner Backup is now version 3 and includes `knowledge_routes`.
Restoring a v3 backup restores the supplemental knowledge file as well.

The System Health check validates the knowledge-route file and the Knowledge Routes UI.
Diagnostic bundles now include `planner/user_knowledge/routes.json`.


## v21.5 — Windows app launcher / real desktop icon

The planner can now be launched like a normal Windows application instead of opening
the app folder and double-clicking a batch file.

### One-time launcher install

Run:

`INSTALL_APP_SHORTCUT.bat`

It adds **Questlog TL Farm Planner** to:
- the Windows Desktop
- the Start Menu

Both use the new `assets/Questlog_TL_Farm_Planner.ico` application icon.

### Optional real EXE

The installer first tries to use the C# compiler included with Windows .NET Framework
to build:

`Questlog TL Farm Planner.exe`

This is a tiny local launcher only. It does not contain or duplicate the scraper/app.
It:
1. checks whether `127.0.0.1:8765` is already running
2. starts `START_APP.bat` if needed
3. waits for `/api/health`
4. opens the planner in the default browser

If the Windows .NET compiler is unavailable, installation still succeeds by creating
the same normal-looking shortcut and icon, backed by the included hidden
`LAUNCH_PLANNER.ps1`.

So the user does **not** need to install Visual Studio or another compiler.

### Browser-tab behavior

The app icon intentionally opens the browser because launching the app is an explicit
request to view it.

The update workflow is unchanged: `APPLY_UPDATE.bat` restarts the server without
opening another browser tab, allowing the already-open planner tab to refresh itself.

### Shortcut removal

`REMOVE_APP_SHORTCUT.bat` removes only the Desktop and Start Menu shortcuts.
It does not delete planner data, cache, the app folder, or the optional launcher EXE.

### Health checks

System Health now verifies that the icon, hidden launcher, shortcut installer/remover,
and EXE builder are present.


## v21.6 — Weekly Planner + Daily Checklist

### Weekly Planner (now Action Plan)
The original **Week Planner** turned recurring EU/Nix Archboss observations into a compact
Monday-Sunday view. In v22.0.15 this surface became the broader **Action Plan**.

It shows:
- Tue/Fri Ascended-pool days
- Wed/Sat Ramux + mixed-pool days
- 19:00 / 22:00 slots
- locally selected mixed-pool slots
- an explicit warning when a future mixed slot is not safely predictable
- the local Boss Priority profile preference for the Ascended pool
- one-click **Open in Boss Priority** for any recurring Archboss day

The weekly view intentionally does **not** guess Peace/Guild assignment. Live event type
must still be confirmed in game before Boss Priority can make an eligibility-aware
recommendation.

The selected week is saved in `data/planner_state.json`.

### Daily Checklist
The Today dashboard now includes an app-owned daily checklist.

On the first visit each calendar day, the planner creates suggestions such as:
- confirm today's Peace/Guild Archboss types
- today's first/full-eligibility Archboss recommendation once configured
- later direct-RNG Archboss target
- current top progression target
- craft-ready item

The player can:
- check/uncheck tasks
- remove any task
- add manual tasks
- Refresh Suggestions after schedule/material changes
- Clear Completed

Checklist state is keyed by the real local calendar date, so a fresh checklist appears
automatically the next day. Recent daily history remains in `planner_state.json`; old
records are pruned automatically to keep the state file small.

Planner Backup already contains all app-owned planner state, so weekly-planner and daily
checklist data are protected automatically.

### System Health
System Health now checks:
- Week Planner rendering
- daily checklist state availability


## v21.7 — Data Freshness + stale-only refresh

### Data Freshness tab
The planner now inspects the actual timestamp of every cached Questlog page referenced by
the latest scan.

The new Data Freshness tab tracks:
- equipped-item DB pages
- expanded route pages
- direct-drop evidence pages
- dungeon-source evidence pages
- container-content pages
- recipe-cost pages
- age of the latest build scan
- last update age for app-owned Knowledge Routes

Each cache category is labeled:
- Fresh
- Getting old
- Stale
- Missing cache
- No data

Knowledge Routes are shown separately as app-owned manual/in-game data and are never
silently treated as stale Questlog evidence.

### Configurable stale threshold
The initial stale threshold is 72 hours (or the configured cache TTL if lower).

The user can change it from 1 to 720 hours in Data Freshness. The choice is saved in
`data/planner_state.json` and therefore included automatically in Planner Backup.

### Refresh Stale Data Only
A new button appears beside normal Scan / Update Build.

A stale-only scan:
1. opens the character builder so equipped-item changes can still be discovered
2. reuses cached Questlog DB/recipe pages younger than the chosen threshold
3. downloads only missing or stale cache pages
4. records how many stale pages were refreshed in live scan statistics

This is intentionally different from Force Refresh:
- Normal scan uses the app's ordinary cache TTL.
- Refresh Stale Data Only uses the user's shorter freshness threshold.
- Force Refresh bypasses cache for every requested DB/recipe page.

### Freshness API
`GET /api/freshness?stale_after_hours=72`

returns category summaries and the stale/missing page list based on the latest successful
scan and current cache timestamps.

### Scan history
New scan-history entries record:
- scan mode
- stale threshold
- scanner cache/download statistics

### System Health
System Health now verifies that the Data Freshness view renders and reports whether
freshness data was loaded for the current scan.


## v21.8 — Centralized Settings

The planner now has a dedicated **Settings** tab plus a Settings button in the always-visible
top scanner controls.

### Startup & UI
Settings include:
- default landing tab
- auto-load latest successful scan
- automatic System Health check

If auto-load is disabled, the top Settings button remains available even before scan-backed
views are loaded.

### Scanning & cache
Settings include:
- default Show Chromium state
- recursive expansion depth
- stale-data threshold
- normal cache lifetime

The normal cache lifetime is written to `config.json` through the local backend and is
applied to the running DiskCache immediately. No server restart is required just to change
the TTL.

Visible Chromium remains the recommended default because Questlog has blocked the headless
browser session before.

### Planner
Settings include:
- automatic Daily Checklist suggestions
- number of Daily Checklist calendar days retained (1–90)
- Guild eligibility default for a newly-created Boss Priority state

Existing Boss Priority state is never overwritten by the Guild default.

Boss event time input remains fixed to explicit 24-hour HH:MM format.

### Safety & recovery
The planner can now require confirmation before Clear Cache. This is enabled by default.

Reset Settings to Defaults affects only preferences. It does **not** delete:
- gear progress
- material inventory
- Sollant
- Boss Priority history
- target gear
- Knowledge Routes
- scan exports
- Questlog cache

### Persistence
UI/planner preferences are stored in `data/planner_state.json`, so they are included in
Planner Backup automatically.

The normal cache TTL remains an application-level setting in `config.json`.


## v21.8.1 — Settings button hotfix + frontend diagnostics

A user diagnostic bundle showed:
- backend v21.8 was running
- planner_state.json already contained the new v21.8 Settings defaults
- config/data/cache/scan/knowledge checks all passed
- the existing diagnostic bundle did not capture browser-side JavaScript errors

The Settings opener has therefore been hardened instead of relying on a synthetic click of
the hidden Settings tab.

### Settings navigation hotfix
All normal tab switching now uses one direct `activateView()` function.

The top **Settings** button:
1. makes the results/view host available
2. selects Settings directly
3. hides the other view hosts
4. renders Settings directly
5. shows a visible error panel if Settings rendering itself fails

This removes the previous indirect `button.click()` path.

### Frontend error diagnostics
The browser now reports:
- uncaught JavaScript errors
- unhandled promise rejections
- view-render failures
- Settings-open failures

to the local backend.

They are saved to:

`data/frontend_errors.log`

and included in future Diagnostic Bundles as:

`logs/frontend_errors.log`

The log is size-bounded automatically.


## v21.8.2 — Quick-action auto-scroll

The v21.8.1 navigation hotfix correctly selected Settings/System Health, but quick-action
buttons at the top of the page left the browser at the scanner controls.

v21.8.2 makes those actions behave like navigation:

- top **Settings** button selects Settings and smoothly scrolls to the planner tab bar
- **Run Health Check** completes the self-test, selects System Health, and smoothly
  scrolls to the planner tab bar
- the selected tab's content begins directly below the tab bar, so the destination is
  immediately visible
- normal clicks on tabs themselves do not force-scroll the page

The scroll runs after the destination view has rendered to avoid jumping to the wrong
position.


## v21.9 — Self-updater foundation

v21.9 is designed to be the last planner update that normally needs the manual
download/extract/APPLY_UPDATE.bat workflow.

### Update source
The planner can use a **public GitHub Releases repository** as its update channel.

Configure the repository once from:

Settings -> Updates -> GitHub update repository

Use `OWNER/REPOSITORY`.

No GitHub access token or password is stored by the planner. Public release checks use the
public GitHub API.

### Recognized release assets
The latest GitHub Release must contain either:
- `Questlog_TL_Farm_Planner_UPDATE.zip`
- the versioned update ZIP, such as `Questlog_TL_Farm_Planner_UPDATE_v21_9.zip`

The release tag should match the app version, for example `v21.9`.

### Safety model
Live install is intentionally conservative:
1. only the configured public GitHub repository is queried
2. only recognized Questlog planner ZIP assets are accepted
3. GitHub must expose a SHA-256 digest for the release asset
4. the downloaded ZIP is independently SHA-256 hashed and must match
5. downloads are capped at 100 MB
6. ZIP paths are checked for traversal/unsafe paths
7. update files are backed up before replacement
8. the server is stopped before the external helper replaces files
9. the external helper restarts the planner
10. the existing browser tab reconnects through the already-built heartbeat system

If a live apply fails, the helper attempts to restore the backup and restart the previous
installation.

`ROLLBACK_LAST_UPDATE.bat` remains available and now also removes files that a live update
introduced when rolling back.

### Update checking
Settings can automatically check GitHub's latest public Release on startup, but updates are
never installed automatically. The player must press **Download & Install**.

The top scanner controls also contain a compact update button/badge.

### Diagnostics
Diagnostic bundles now include live-update download/result state when present.
System Health reports the last live-update result.


## v21.9.1 — Live update end-to-end test

This is intentionally a tiny release used to verify the v21.9 GitHub self-updater.

Visible confirmation:
- app version becomes v21.9.1
- header subtitle shows `LIVE UPDATE TEST PASSED`
- Settings -> Updates shows a green test-success callout

No planner data model, Questlog scrape logic, cache, gear state, Knowledge Routes,
Boss Priority logic, or settings are changed by this test release.


## v21.9.2 — Live update restart/reconnect fix

The first v21.9 -> v21.9.1 live update proved that GitHub detection, download,
SHA-256 verification, backup and file replacement worked, but the local server did not
reliably restart afterward. The player had to use the app launcher manually.

v21.9.2 hardens both halves of that final step.

### Server restart
- `START_APP.bat` now starts the venv Python launcher directly rather than through a
  nested `cmd /c` server chain.
- This matters immediately because the v21.9.1 live helper invokes the newly-applied
  START_APP.bat after copying v21.9.2.
- The new v21.9.2 `LIVE_UPDATE_HELPER.py` goes further for future releases:
  - starts `.venv\Scripts\python.exe launcher.py` directly
  - uses a new console/process group
  - waits for `/api/health`
  - falls back to START_APP.bat if the direct launch does not become ready
  - logs restart attempts to `data/live_update_restart.log`

### Browser reconnect
For future live updates the browser now:
- starts an explicit 750ms reconnect watcher as soon as update apply begins
- keeps the existing 2-second general heartbeat as a fallback
- checks again when the tab receives focus or becomes visible
- uses a cache-busting `location.replace()` when the new server version appears

Diagnostic Bundles now include:
`updates/live_update_restart.log`

if it exists.


## v21.9.3 — End-to-end live update verification

This release intentionally changes almost nothing beyond the version and visible test message.

It must be installed from inside an already-running v21.9.2 planner so that the new
v21.9.2 live-update helper performs the entire flow:

1. detect v21.9.3 from GitHub Releases
2. download the release asset
3. verify GitHub's SHA-256 digest
4. validate the ZIP
5. back up changed files
6. stop the old local server
7. apply the update
8. restart via direct venv Python launch
9. confirm `/api/health`
10. let the already-open browser tab reconnect and cache-busting reload itself

Success criteria: the browser should show v21.9.3 automatically without manually launching
the app or refreshing the page.


## v22.0 — Navigation / workspace polish

v22.0 is the first normal feature release delivered after the live updater was verified.

The goal is not another subsystem; it is making the existing planner easier to navigate.

### Grouped sticky workspace navigation
The long flat tab row is now grouped into:
- **Plan** — Farm Dashboard, Boss Priority, Week Planner
- **Progress** — Farm Plan, Upgrade Paths, Knowledge Routes
- **Data** — Container Contents, Scan History, Data Freshness
- **System** — System Health, Settings, Raw JSON

On desktop the workspace navigation stays visible while scrolling through long planner
views. It falls back to normal non-sticky layout on narrower displays.

The current view name is shown above the navigation and is also reflected in the browser
tab title.

### Cleaner scanner controls
Routine scan actions remain visible:
- Show Chromium
- Force Refresh
- Scan / Update Build
- Refresh Stale Data Only
- Load Last Scan
- Cancel
- Settings
- Update status

Less-frequent destructive/support actions now live under:
**Maintenance & diagnostics**
- Clear Cache
- Download Diagnostic Bundle

No button IDs or backend actions were removed.

### Cleaner result controls
Routine slot/health controls stay visible.

JSON export and planner backup/restore are grouped under:
**Exports & recovery**

### Long-page navigation
A floating **Back to top** button appears after scrolling down a long planner page.

### System Health
System Health now verifies the four grouped workspace navigation sections and the
back-to-top control.


## v22.0.1 — Settings deep-link + scrollspy navigation

### Check for Updates deep-link
The top **Check for Updates / Update Available** control is now a true shortcut to:

`Settings -> Updates`

It no longer stops at the top of the Settings page.

The navigation waits for the Settings DOM to render, calculates an offset for the sticky
workspace navigation, and then scrolls directly to the Updates section.

If the update check itself causes Settings to re-render, the app re-anchors to Updates
after the check finishes.

### Settings scrollspy
The Settings sidebar now follows the user's actual scroll position.

For example:
- scroll into Startup & UI -> Startup & UI becomes active
- continue into Scanning & Cache -> Scanning & Cache becomes active
- reach Updates -> Updates becomes active
- scroll back upward -> the highlight follows back upward automatically

Clicking a sidebar section still smooth-scrolls to that section.

### Sticky offset
The Settings sidebar now dynamically offsets itself below the sticky v22.0 workspace
navigation rather than using a fixed 10px top position.

### System Health
System Health validates that all six Settings sections are registered with deep-link
scrolling and scroll-position tracking.


## v22.0.2 — Settings sticky-header overlap fix

The v22.0 grouped workspace navigation is useful on long planner pages, but keeping it
sticky while Settings also has its own sticky sidebar caused the workspace header to cover
the top of Settings content and partially obscure the left-side Settings categories.

v22.0.2 changes the behavior specifically for Settings:

- the grouped workspace navigation remains sticky in normal planner views
- while **Settings** is active, the grouped workspace navigation becomes non-sticky
- the Settings sidebar becomes the only sticky navigation in that view
- the Settings sidebar uses a normal 10px viewport offset
- switching away from Settings immediately restores the normal sticky workspace navigation

No Settings category, update shortcut, scrollspy behavior, or grouped workspace section is
removed.


## v22.0.3 — Settings scroll alignment + stable section tracking

The previous Settings scrollspy switched sections too close to the top edge of the viewport.
That could make the left-side highlight feel slightly ahead/behind the content being read.

It also allowed a short section such as **Updates** to be skipped when both Updates and
App Behavior were visible at the same time.

v22.0.3 changes the model:

- Settings uses a reading focus point around 24% down the viewport.
- Each section owns the range between the midpoint to the previous section heading and the
  midpoint to the next section heading.
- Short sections therefore still get a real active range and cannot be skipped merely
  because the next section is also visible.
- Clicking a Settings category leaves more breathing room above its heading.
- The final App Behavior section is only forced active at the page bottom after its heading
  has actually entered the viewport.

This keeps the sidebar highlight better aligned with what the player is actually reading.


## v22.0.4 — Summary/action spacing polish

A small visual cleanup to the scan-summary panel:

- adds more vertical breathing room between the four summary cards and
  **Expand All Slots / Collapse All Slots / Run Health Check**
- slightly balances spacing around **Exports & recovery**
- slightly balances the scan/planner-state metadata line

No behavior, data, scanner logic, Settings navigation, or updater logic changes.


## v22.0.5 - Refresh-loop and GitHub backoff safety

This release hardens the planner's same-tab reconnect and public GitHub update checks.

- Frontend/backend version values must both be valid `X.Y.Z` versions before a mismatch
  can trigger an automatic refresh.
- A version mismatch can trigger only one automatic refresh per browser session, so a
  stale or malformed page cannot trap the user in a reload loop.
- Persistent mismatches stop safely and display a restart message while leaving the full
  planner scrollable.
- Successful GitHub release checks are cached for five minutes.
- GitHub `403`/`429` rate-limit responses honor `Retry-After` and
  `X-RateLimit-Reset`, with a one-minute minimum backoff when neither is supplied.
- Retry notices use the PC's local time and UTC offset.
- Expected rate limiting appears as an amber **Retry later** state and is not recorded as
  a frontend application error.

Planner data, cached Questlog pages, scan history, progress, priorities, materials,
Sollant, weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.6 - Reliable update navigation

This release fixes the top **Check for Updates** navigation shortcut.

- Clicking **Check for Updates** reliably opens **Settings** at the **Updates** section.
- The requested Settings destination is captured before smooth scrolling begins.
- Settings scrollspy updates and update-check re-renders can no longer retarget the jump
  to an earlier section such as **Scanning & Cache**.

Planner data, cached Questlog pages, scan history, progress, priorities, materials,
Sollant, weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.7 - Fluid motion-aware navigation

This release gives the planner one consistent scrolling system.

- Workspace tabs, Settings sections, item cards, and **Back to top** now use one
  shared motion controller.
- A newer navigation click cancels an older pending or active scroll.
- Item headings stop below the sticky workspace navigation on desktop and use a
  compact offset when the navigation is no longer sticky.
- Settings keeps the requested section highlighted while moving through intermediate
  sections, preventing scrollspy flicker during programmatic navigation.
- Mouse-wheel, touch, and keyboard scrolling immediately return control to the user.
- Windows and browser reduced-motion preferences disable smooth animation automatically.

Planner data, cached Questlog pages, scan history, progress, priorities, materials,
Sollant, weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.8 - Flowing navigation and activity feedback

This release makes movement feel more natural and adds one place to follow important
planner actions.

- Native browser smooth scrolling is replaced with a distance-aware eased animation:
  short jumps remain quick while long jumps glide longer and settle gently.
- A newer click, mouse wheel, touch gesture, or keyboard scroll cancels the active
  animation immediately.
- Reduced-motion preferences still switch every navigation jump to instant movement.
- A compact **Activity** button shows unread feedback without changing the current view.
- The activity panel keeps up to 30 notices for the current browser-tab session and
  survives same-tab refreshes, including updater reconnects.
- Saves, scans, updates, backups, diagnostics, cache actions, warnings, and failures now
  produce non-blocking toasts and activity entries.
- Disruptive browser alert messages are removed; destructive actions continue to require
  explicit confirmation.

Planner data, cached Questlog pages, scan history, progress, priorities, materials,
Sollant, weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.9 - Inertial wheel scrolling and official 4.7.0 context

This release extends the motion controller to physical mouse-wheel input and records
the planner impact of the official Throne and Liberty Update 4.7.0 notes.

### Mouse-wheel motion

- Discrete wheel steps accumulate into one smoothly eased destination instead of moving
  the page in rigid jumps.
- The glide remains interruptible by new navigation, keyboard input, or touch; a change
  in wheel direction immediately retargets the eased destination.
- Nested activity panels, update notes, form controls, and other independently scrollable
  areas retain their native behavior.
- Small precision-touchpad deltas remain native because those devices already provide
  smooth pixel-level motion.
- Reduced-motion preferences continue to disable animation.

### Official Update 4.7.0 context

- Ascended Talandre and Nix Field Boss weapon drop rates increased, but the official notes
  did not publish numeric percentages.
- Ramux gained three equipment rewards and ten Skill Cores, including Wand: Nightmare
  Melody and Gauntlets: Crimson Imprint.
- Talandre and Nix Guild Raid rewards increased; personal eligibility is still required.
- Trait Unlockstone and Trait Enchantment Stone crafting fees fell from 218,180 to
  43,000 Sollant each.
- A Remnants of Nix issue that could prevent Redfrost Item acquisition after a death was
  fixed.
- Expanded Helping Hand rewards and new pre-Nix Gear Lithographs are shown as context but
  are not auto-scored without exact reward contents and item mappings.

The planner does not invent drop rates or automatically alter boss scores from qualitative
patch-note wording. Planner data, cached Questlog pages, scan history, progress, priorities,
materials, Sollant, weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.10 - Faster wheel motion and Patch Impact Inbox

This release quickens the inertial wheel curve and turns official patch-note context into
a structured review workflow with stronger visual hierarchy.

### Faster fluid scrolling

- The wheel easing time constant drops from 105 ms to 88 ms, making the visible glide
  about 16% quicker without returning to rigid native wheel jumps.
- Discrete steps still accumulate and direction changes still retarget the destination.
- Precision touchpads, nested scroll areas, form controls, and reduced-motion preferences
  retain their native behavior.

### Patch Impact Inbox

- Adds a dedicated Plan tab for six confirmed Update 4.7.0 impacts.
- A spacious patch hero, four summary tiles, filter chips, and two-column impact cards
  create the visual breaks and scan-friendly rhythm inspired by the supplied layout video.
- Every impact separates confirmed patch-note evidence from the proposed planner action.
- Review status persists as Needs review, Watching, or Reviewed in planner_state.json.
- Compact patch banners on the Farm Dashboard and Boss Priority pages replace the earlier
  dense patch-note list and open the inbox directly.
- Mobile layouts collapse the impact cards and evidence/action panels to one column.

Review states are organizational only. They do not automatically change boss weights,
drop percentages, recipe costs, planner data, cached Questlog pages, scan history,
progress, priorities, materials, Sollant, weekly/daily state, backups, or user knowledge.


## v22.0.11 - Friendly planner identity and visual workspace

This release reshapes the planner from a diagnostic-looking utility into a more welcoming,
purpose-led progression workspace without removing any existing controls.

### Original visual identity

- Adds an original route-and-waypoint emblem that forms a subtle Q and represents planning,
  progression, and reaching a destination.
- Uses the emblem in the product header, browser favicon, and a restrained dashboard watermark.
- Introduces a midnight-navy, violet, sky-blue, and warm-gold visual language inspired by
  the supplied Questlog layout video without copying its brand or page composition.
- Packages the logo as a required live-update asset and verifies that it loads in System Health.

### Friendlier planner experience

- Rebuilds the top of the app as a branded product hero with a clearer purpose statement.
- Turns the scanner into a focused Build Source drawer. It remains open before a build is
  available and automatically compacts after the loaded scan renders.
- Turns the detailed Build Overview and Upgrade Queue into an optional gear-management drawer,
  so returning users reach the daily plan sooner.
- Adds a visual build-completion ring and stronger purpose-led cards to Today's Route.
- Softens borders, increases spacing, clarifies typography, and removes equal visual weight
  from maintenance controls, summary information, navigation, and daily priorities.
- Simplifies sticky workspace navigation while preserving every Plan, Progress, Data, and
  System view on desktop and compact layouts.

Planner data, cached Questlog pages, scan history, progress, priorities, materials, Sollant,
weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.12 - Revolving planner promise and context-aware workspace header

This release adapts the supplied Questlog header references into an original planner-specific
navigation system and adds a reduced-motion-aware revolving goal beneath the product name.

### Revolving planner promise

- Keeps the fixed phrase “Plan your” in place while next upgrade, boss priorities, crafting
  route, and weekly goals transition vertically.
- Uses a brief slide-out, clear, and slide-in sequence matching the supplied interaction idea
  without copying Questlog text, branding, or assets.
- Stops the animation for reduced-motion users and leaves the first phrase readable.
- Avoids live-region announcements so repeated decorative changes do not interrupt screen readers.

### Context-aware workspace header

- Replaces the permanently visible workspace button grid with a compact two-level app header.
- Adds live completion, next-target, patch-review, and health context sourced from the actual
  loaded planner state.
- Keeps Overview directly available and groups the remaining views into Plan, Progress,
  Library, and System menus with icons, descriptions, and clear current-view state.
- Supports pointer hover, mouse click, touch tap, Escape, outside-click closing, focus return,
  and automatic closing after a destination is selected.
- Uses a two-column live-context rail and one-column menu destinations on compact screens.
- Routes card shortcuts through the same view controller so menu highlighting and current-view
  labels remain correct when navigation starts elsewhere in the planner.

Planner data, cached Questlog pages, scan history, progress, priorities, materials, Sollant,
weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.13 - Visual dashboard mission control

This release turns the Farm Dashboard from a set of similarly weighted text panels into a
clear visual route from the current objective to the deeper planner evidence behind it.

### Primary objective command deck

- Promotes the top saved planner target into a dominant objective card with its real item
  artwork, intent or priority badge, current gap, and direct route action.
- Visualizes Target locked → Current action → Finish upgrade as a three-step path instead
  of requiring the user to infer that flow from several panels.
- Adds a direct Open objective shortcut that routes to the exact Farm Plan item or Upgrade
  Path through the shared view controller.
- Adds three readiness pulses for crafting, Boss Priority, and Sollant coverage.
- Adds a four-stage Not started / Farming / Ready / Complete rail sourced from live build state.

### Clearer supporting hierarchy

- Replaces the former four equal Today's Route text cards with three compact support cards
  for the boss window, craft readiness, and the next queued route.
- Introduces a quieter “Details when you need them” transition below the daily checklist.
- Gives budget, target, activity, and material panels distinct icons, subtle color identities,
  and shorter descriptions while retaining their full data and controls.
- Collapses the command deck, readiness pulses, status rail, and support cards cleanly for
  compact windows without horizontal overflow.
- Adds a dedicated System Health check for the responsive command deck, route stages, pulses,
  and objective shortcut.

Planner data, cached Questlog pages, scan history, progress, priorities, materials, Sollant,
weekly/daily state, backups, and user knowledge are unchanged.


## v22.0.14 - Cinematic backdrop and larger workspace controls

This release gives the planner's empty space environmental depth and enlarges the workspace
header so it reads as a primary application control surface.

### Original atmospheric backdrop

- Adds an original cinematic fantasy basin with misty cliffs, distant bridges, and a celestial
  observatory; it does not reproduce Questlog or Throne and Liberty artwork, locations, logos,
  characters, or interface assets.
- Places the environment beneath a fixed midnight-navy transparency gradient so it remains
  atmospheric behind long pages without competing with planner text.
- Uses restrained translucent panels, blur, stronger edge definition, and a slightly clearer
  product hero to create the requested image-under-dark-glass effect.
- Keeps the composition quiet through the center and detailed around the edges so content-heavy
  panels remain readable while page gaps feel occupied.

### Larger workspace header

- Enlarges the live context rail to 54 px and the primary navigation row to 72 px on desktop.
- Increases context icons, value labels, category labels, the mini planner brand, navigation
  targets, and the current-view indicator.
- Retains the compact two-column context rail, wrapped navigation, and readable dashboard flow
  without horizontal overflow.
- Packages the new image through the strict live-update allowlist and requires it during ZIP
  validation so the installed UI cannot silently lose its background.
- Adds a System Health check for the cinematic asset and enlarged desktop proportions.

The background was generated with the built-in image generation tool and saved as
`static/assets/planner-astral-basin-v1.png`. Planner data, cached Questlog pages, scan history,
progress, priorities, materials, Sollant, weekly/daily state, backups, and user knowledge are
unchanged.


## v22.0.15 - Time-budgeted Action Plan and readable workspace menus

The former Week Planner is now a build-aware Action Plan Engine. It turns the player's actual
unfinished targets into a practical weekly route instead of showing the boss calendar alone.

### Action Plan Engine

- Accepts a weekly playtime budget, preferred session length, focus mode, and available days.
- Builds deterministic sessions from unfinished planner targets, priority crafting allocation,
  current daily-checklist tasks, useful acquisition activities, and observed Archboss windows.
- Offers direct shortcuts for a 30-minute window, tonight's best move, and the current
  progression route.
- Lets the player check off planned sessions independently from gear progress or inventory.
- Can add any recommendation to today's checklist or open its exact Farm Plan, Upgrade Path,
  Dashboard, or Boss Priority route.
- Preserves the recurring schedule as collapsible evidence and continues to require live
  Peace/Guild confirmation rather than guessing event eligibility.

### More readable grouped navigation

- Enlarges workspace group titles, descriptions, destination names, supporting copy, and icons.
- Raises contrast on secondary menu descriptions and gives each destination more breathing room.
- Keeps the compact one-column menu behavior on narrow windows.

System Health now verifies the Action Plan functions, all seven availability controls, and the
minimum workspace destination text size. Planner build data, scan history, gear progress,
inventory, backups, and user knowledge remain unchanged.


## v22.0.16 - Scan Change Briefing and guarded 2x boss-drop scenario

### Scan Change Briefing

- Adds a visual briefing above Scan History after every successful refresh.
- Compares exact probability values, crafting recipes, acquisition-route categories, equipment,
  and general Questlog evidence against the previous scan for the same build URL.
- Maps changed item names back to active Action Plan targets so the player can see whether the
  weekly route needs to be re-ranked.
- Keeps canonical before/after probability values visible in each history entry.
- Clearly marks older history entries that predate detailed probability comparisons.

### Update 4.7.0 community scenario

The official notes confirm increased weapon drop rates for Ascended Talandre and Nix Field
Bosses, but they do not publish a percentage or multiplier. The supplied video analysis argues
for a 2x interpretation from historical patterns.

The planner therefore provides a switchable **2x community working scenario**:

- matching loaded-build rows show Questlog's canonical percentage beside the modeled 2x value;
- relevant routes receive only a modest ranking signal while the scenario is enabled;
- every scenario label says that the multiplier is not an official numeric claim;
- scraped Questlog percentages are never changed or replaced;
- later scans can confirm or contradict the scenario through exact before/after comparisons.

System Health verifies both the detailed scan briefing and the scenario guard. Existing scan
files, planner state, progress, inventory, backups, and user knowledge remain intact.
