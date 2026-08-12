from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, urlunparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE = "https://questlog.gg"


class ScanCancelled(Exception):
    pass


def clean_url(url: str) -> str:
    url = urldefrag(url or "")[0]
    if url.startswith("/"):
        url = urljoin(BASE, url)
    return url.rstrip("/")


def identity_url(url: str) -> str:
    """Canonical identity for comparing Questlog DB records.

    Important v16 fix:
    ?level= and ?level=57 are presentation parameters and must NOT prevent
    a recipe Result URL from matching the item page.
    """
    p = urlparse(clean_url(url))
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/").lower(), "", "", ""))


def same_url(a: str, b: str) -> bool:
    return identity_url(a) == identity_url(b)


def is_db_item(url: str) -> bool:
    return "/db/item/" in urlparse(url).path.lower()


class DiskCache:
    def __init__(self, cache_dir: Path, ttl_hours: int = 168):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)

    def _path(self, url: str) -> Path:
        h = hashlib.sha256(identity_url(url).encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _entry(self, url: str):
        p = self._path(url)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(data["_cached_at"])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return {
                "path": p,
                "data": data,
                "cached_at": stamp,
                "age": datetime.now(timezone.utc) - stamp,
            }
        except Exception:
            return None

    def metadata(self, url: str):
        entry = self._entry(url)
        if entry is None:
            return {
                "exists": False,
                "cached_at": None,
                "age_hours": None,
                "ttl_fresh": False,
            }

        age_hours = max(0.0, entry["age"].total_seconds() / 3600.0)
        return {
            "exists": True,
            "cached_at": entry["cached_at"].isoformat(),
            "age_hours": age_hours,
            "ttl_fresh": entry["age"] <= self.ttl,
        }

    def get(self, url: str, max_age_hours=None):
        entry = self._entry(url)
        if entry is None:
            return None

        max_age = self.ttl
        if max_age_hours is not None:
            try:
                requested = timedelta(hours=max(0.0, float(max_age_hours)))
                if requested < max_age:
                    max_age = requested
            except Exception:
                pass

        if entry["age"] > max_age:
            return None

        try:
            return entry["data"]["payload"]
        except Exception:
            return None

    def put(self, url: str, payload):
        p = self._path(url)
        p.write_text(
            json.dumps(
                {
                    "_cached_at": datetime.now(timezone.utc).isoformat(),
                    "url": url,
                    "identity_url": identity_url(url),
                    "payload": payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def clear(self):
        count = 0
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
                count += 1
            except Exception:
                pass
        return count


class QuestlogScraper:
    def __init__(self, config: dict, cache: DiskCache, progress=None, should_cancel=None):
        self.config = config
        self.cache = cache
        self.progress = progress or (lambda **kwargs: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.stats = {
            "pages_requested": 0,
            "pages_cache_hit": 0,
            "pages_downloaded": 0,
            "pages_stale_refreshed": 0,
        }
        self.browser_visible = None
        self.stale_after_hours = None

    def check_cancel(self):
        if self.should_cancel():
            raise ScanCancelled("Scan cancelled by user.")

    def emit(self, message: str, **extra):
        self.progress(message=message, **extra)

    def open_rendered(self, page, url):
        self.check_cancel()
        self.emit(f"Opening {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.config["page_timeout_ms"])
        except PlaywrightTimeoutError:
            self.emit("Page load timed out; continuing with rendered content.")
        page.wait_for_timeout(self.config["after_load_wait_ms"])
        self.check_cancel()

        try:
            txt = page.locator("body").inner_text(timeout=2500).lower()
        except Exception:
            txt = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""

        cloudflare_block = (
            "sorry, you have been blocked" in txt
            or ("attention required" in title and "cloudflare" in title)
            or "you are unable to access questlog.gg" in txt
        )
        if cloudflare_block:
            if self.browser_visible is False:
                raise RuntimeError(
                    "Questlog/Cloudflare blocked the headless Chromium session. "
                    "The app will not attempt to bypass this security check. "
                    "Turn ON 'Show Chromium while scanning' and try again."
                )
            raise RuntimeError(
                "Questlog/Cloudflare blocked this Chromium session. "
                "The app stopped without trying to bypass the security check."
            )

        if any(x in txt for x in ("captcha", "verify you are human", "access denied", "cloudflare challenge")):
            raise RuntimeError("Questlog access-control page detected. Scan stopped.")

    def trigger_lazy_sections(self, page):
        try:
            page.evaluate("window.scrollTo(0,0)")
        except Exception:
            return

        last_h = 0
        stable = 0

        for _ in range(self.config["max_scroll_steps"]):
            self.check_cancel()
            try:
                info = page.evaluate(
                    """() => ({
                      y: window.scrollY,
                      h: document.documentElement.scrollHeight,
                      vh: window.innerHeight
                    })"""
                )
                h, y, vh = int(info["h"]), int(info["y"]), int(info["vh"])
                stable = stable + 1 if h == last_h else 0
                last_h = h
                ny = min(h, y + int(vh * 0.78))
                page.evaluate("(y)=>window.scrollTo(0,y)", ny)
                page.wait_for_timeout(self.config["scroll_wait_ms"])
                if ny + vh >= h - 10 and stable >= 2:
                    break
            except Exception:
                break

        page.wait_for_timeout(self.config["after_scroll_wait_ms"])

    def click_equipment_tab(self, page):
        try:
            x = page.get_by_text(re.compile(r"^\s*Equipment\s*$", re.I)).first
            if x.count() and x.is_visible():
                x.click(timeout=2500)
                page.wait_for_timeout(700)
        except Exception:
            pass

    def locate_equipment_grid(self, page):
        grids = page.locator("div.grid.grid-cols-3")
        matches = []
        for i in range(grids.count()):
            g = grids.nth(i)
            try:
                kids = g.locator(":scope > div.cursor-pointer")
                named = sum(
                    1 for j in range(kids.count())
                    if kids.nth(j).locator('img[alt]:not([alt=""])').count()
                )
                if kids.count() >= 10 and named >= 10:
                    matches.append((g, kids.count()))
            except Exception:
                pass

        if not matches:
            return None
        matches.sort(key=lambda x: abs(x[1] - 15))
        return matches[0][0]

    def slot_name(self, slot):
        imgs = slot.locator('img[alt]:not([alt=""])')
        for i in range(imgs.count()):
            alt = (imgs.nth(i).get_attribute("alt") or "").strip()
            if alt:
                return alt
        return ""

    def slot_icon(self, slot):
        """Return the equipped item's visible Questlog image URL when available."""
        imgs = slot.locator('img[alt]:not([alt=""])')
        for i in range(imgs.count()):
            img = imgs.nth(i)
            src = (img.get_attribute("src") or "").strip()
            if src:
                return clean_url(urljoin(BASE, src))
        return None

    def get_view_db_url(self, page):
        links = page.locator('a[href*="/db/item/"]', has_text="View in Database")
        for i in range(links.count()):
            a = links.nth(i)
            href = a.get_attribute("href")
            if href:
                u = clean_url(urljoin(page.url, href))
                if is_db_item(u):
                    return u
        return None

    def wait_for_equipment_grid(self, page, timeout_ms=15000):
        """Wait for the character-builder equipment grid to actually render.

        Questlog's character builder can finish DOMContentLoaded before the equipment
        component exists, especially in headless Chromium. We therefore keep checking
        the Equipment tab/grid instead of assuming the first 2.2s render is complete.
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        attempt = 0

        while time.time() < deadline:
            self.check_cancel()
            attempt += 1

            try:
                self.click_equipment_tab(page)
            except Exception:
                pass

            g = self.locate_equipment_grid(page)
            if g is not None:
                return g

            self.emit(
                f"Waiting for Questlog equipment grid… ({attempt})",
                phase="build_wait",
                current_item="Loading build…",
                stats=dict(self.stats),
            )

            # Nudge lazy/client rendering without aggressively crawling the page.
            try:
                page.evaluate("window.scrollTo(0, Math.min(700, document.documentElement.scrollHeight))")
            except Exception:
                pass
            page.wait_for_timeout(650)

        return None

    def discover_build(self, page, build_url):
        self.open_rendered(page, build_url)

        g = self.wait_for_equipment_grid(page, timeout_ms=15000)

        # One controlled retry helps when Questlog's client-side builder hydration
        # silently fails on the first navigation.
        if g is None:
            self.emit(
                "Equipment grid did not render; retrying the build page once…",
                phase="build_retry",
                current_item="Reloading build…",
                stats=dict(self.stats),
            )
            try:
                page.reload(wait_until="domcontentloaded", timeout=self.config["page_timeout_ms"])
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(1800)
            g = self.wait_for_equipment_grid(page, timeout_ms=12000)

        if g is None:
            try:
                title = page.title()
            except Exception:
                title = ""
            try:
                body = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=2000)).strip()[:500]
            except Exception:
                body = ""
            raise RuntimeError(
                "Equipment grid not found after retry. "
                f"Page title: {title!r}. Visible text: {body!r}"
            )

        n = g.locator(":scope > div.cursor-pointer").count()
        self.emit(f"Found {n} equipment slots.", phase="build", current=0, total=n)

        found = {}
        for i in range(n):
            self.check_cancel()
            g = self.locate_equipment_grid(page)
            s = g.locator(":scope > div.cursor-pointer").nth(i)
            name = self.slot_name(s)
            icon_url = self.slot_icon(s)

            try:
                s.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

            try:
                s.click(timeout=5000)
            except Exception:
                s.evaluate("e=>e.click()")

            page.wait_for_timeout(self.config["slot_change_wait_ms"])

            url = None
            for _ in range(8):
                url = self.get_view_db_url(page)
                if url:
                    break
                page.wait_for_timeout(200)

            if url:
                found[name] = {"slot_index": i, "url": url, "icon_url": icon_url}
                self.emit(
                    f"{i+1}/{n}: {name}",
                    phase="build",
                    current=i + 1,
                    total=n,
                )

        return found

    def headers(self, table):
        try:
            return [
                re.sub(r"\s+", " ", x).strip()
                for x in table.locator("thead th").all_inner_texts()
                if x.strip()
            ]
        except Exception:
            return []

    def page_item_icon(self, page):
        """Best-effort item icon discovery from Questlog DB item pages."""
        selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count():
                    content = (loc.first.get_attribute("content") or "").strip()
                    if content:
                        return clean_url(urljoin(page.url, content))
            except Exception:
                pass

        # Fallback: prefer visible item imagery, excluding tiny/nav images.
        try:
            imgs = page.locator('img[src*="/Icon/Item_"], img[src*="/Item_128/"]')
            for i in range(min(imgs.count(), 20)):
                src = (imgs.nth(i).get_attribute("src") or "").strip()
                if src:
                    return clean_url(urljoin(page.url, src))
        except Exception:
            pass
        return None

    def parse_table(self, table, index):
        hs = self.headers(table)
        rows = []
        trs = table.locator("tbody tr")

        for ri in range(trs.count()):
            tr = trs.nth(ri)
            cells = tr.locator("td")
            row = {"row_index": ri, "cells": []}

            for ci in range(cells.count()):
                td = cells.nth(ci)

                try:
                    txt = re.sub(r"\s+", " ", td.inner_text()).strip()
                except Exception:
                    txt = ""

                links = []
                aa = td.locator("a[href]")

                for ai in range(aa.count()):
                    a = aa.nth(ai)
                    href = a.get_attribute("href") or ""

                    try:
                        atxt = re.sub(r"\s+", " ", a.inner_text()).strip()
                    except Exception:
                        atxt = ""

                    try:
                        alts = [
                            x for x in a.locator('img[alt]').evaluate_all(
                                "els=>els.map(e=>e.alt||'')"
                            ) if x
                        ]
                    except Exception:
                        alts = []

                    try:
                        image_srcs = [
                            clean_url(urljoin(BASE, x))
                            for x in a.locator('img[src]').evaluate_all(
                                "els=>els.map(e=>e.getAttribute('src')||'')"
                            ) if x
                        ]
                    except Exception:
                        image_srcs = []

                    amount = None
                    try:
                        amt = a.locator(".image-amount")
                        if amt.count():
                            amount = re.sub(r"\s+", " ", amt.first.inner_text()).strip()
                    except Exception:
                        pass

                    links.append(
                        {
                            "text": atxt,
                            "url": clean_url(urljoin(BASE, href)),
                            "image_alts": alts,
                            "image_srcs": image_srcs,
                            "amount": amount,
                        }
                    )

                key = hs[ci] if ci < len(hs) else f"Column {ci+1}"
                row["cells"].append({"header": key, "text": txt, "links": links})
                row[key] = txt

            rows.append(row)

        return {"table_index": index, "headers": hs, "row_count": len(rows), "rows": rows}

    @staticmethod
    def cell(row, name):
        for c in row["cells"]:
            if c["header"].lower() == name.lower():
                return c
        return None

    def urls_in_cell(self, row, name):
        c = self.cell(row, name)
        if not c:
            return []
        return [clean_url(x.get("url", "")) for x in c.get("links", []) if x.get("url")]

    @staticmethod
    def first_col_urls_names(t):
        urls, names = [], []
        for r in t["rows"]:
            if not r["cells"]:
                continue
            names.append(r["cells"][0].get("text", ""))
            for l in r["cells"][0].get("links", []):
                urls.append(clean_url(l.get("url", "")))
        return urls, names

    def classify_table_shape(self, t):
        hs = [x.lower() for x in t["headers"]]
        urls, names = self.first_col_urls_names(t)
        lowu = [x.lower() for x in urls]
        lown = [x.lower() for x in names]

        if hs == ["name", "type", "quantity", "probability", "drop type", "drop condition"]:
            return "Direct Drops"

        if hs == ["name", "difficulty"] and any("/db/dungeon/" in u for u in lowu):
            return "Dungeon Sources"

        if hs == ["name", "materials", "result"]:
            if any("/db/litograph/" in u for u in lowu):
                return "Litographs"
            return "Recipe Relations"

        if hs == ["name", "quantity", "drop type"]:
            return "Containers / Reward Chests"

        # v16 discovery: these are usually the CONTENTS of a container,
        # not a route to obtain the current container.
        if hs == ["name", "quantity", "drop type", "probability"]:
            return "Container Contents"

        if hs == ["name"]:
            if any("/db/item/perk_" in u for u in lowu) or any(n.startswith("skill core:") for n in lown):
                return "Skill Cores"
            if any("/db/skill-set/" in u for u in lowu):
                return "Skill Sets"
            return "Related Items"

        if hs and hs[0] == "level":
            return "Base Stats"

        return "Other"

    @staticmethod
    def dedupe_rows(rows):
        seen = set()
        out = []

        for r in rows:
            sig = []
            for c in r["cells"]:
                sig.extend([c.get("header", ""), c.get("text", "")])
                for l in c.get("links", []):
                    sig.extend([identity_url(l.get("url", "")), l.get("amount") or ""])
            key = tuple(sig)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)

        return out

    def analyze_tables_for_page(self, page_url, tables):
        acquisition = []
        contents = []
        non_acquisition = []

        for t in tables:
            shape = self.classify_table_shape(t)
            rows = self.dedupe_rows(t["rows"])

            if shape in ("Direct Drops", "Dungeon Sources", "Containers / Reward Chests"):
                acquisition.append({"kind": shape, "rows": rows, "headers": t["headers"]})
                continue

            if shape == "Container Contents":
                contents.append({"kind": shape, "rows": rows, "headers": t["headers"]})
                continue

            if shape == "Recipe Relations":
                creates, uses, ambiguous = [], [], []

                for r in rows:
                    result_urls = self.urls_in_cell(r, "Result")
                    material_urls = self.urls_in_cell(r, "Materials")

                    if any(same_url(u, page_url) for u in result_urls):
                        creates.append(r)
                    elif any(same_url(u, page_url) for u in material_urls):
                        uses.append(r)
                    else:
                        ambiguous.append(r)

                if creates:
                    acquisition.append({"kind": "Craftable From", "rows": creates, "headers": t["headers"]})
                if uses:
                    non_acquisition.append({"kind": "Used By Recipes", "rows": uses, "headers": t["headers"]})
                if ambiguous:
                    non_acquisition.append({"kind": "Ambiguous Recipe Relations", "rows": ambiguous, "headers": t["headers"]})
                continue

            non_acquisition.append({"kind": shape, "rows": rows, "headers": t["headers"]})

        return acquisition, contents, non_acquisition

    @staticmethod
    def cached_container_icons_are_legacy(record):
        """True when an old cached container table lacks linked image URLs.

        v20.2 began storing the image src from Questlog table links. Older cache
        records only contain image alt text, so container drop icons cannot render.
        We selectively refresh only cached pages that actually contain container
        content rows with missing image metadata.
        """
        contents = (record or {}).get("container_contents", [])
        if not contents:
            return False

        for rel in contents:
            for row in rel.get("rows", []):
                for cell in row.get("cells", []):
                    for link in cell.get("links", []):
                        if link.get("url") and not link.get("image_srcs"):
                            return True
        return False

    def cache_lookup(self, url, force_refresh=False):
        """Return (payload, metadata, stale_refresh).

        stale_refresh is true when a cache file exists but the current stale-only
        threshold intentionally rejects it.
        """
        meta = self.cache.metadata(url)

        if force_refresh:
            return None, meta, False

        cached = self.cache.get(url, max_age_hours=self.stale_after_hours)

        stale_refresh = bool(
            cached is None
            and self.stale_after_hours is not None
            and meta.get("exists")
            and meta.get("age_hours") is not None
            and meta.get("age_hours") > float(self.stale_after_hours)
        )
        return cached, meta, stale_refresh

    def scrape_page(self, page, url, force_refresh=False):
        self.check_cancel()
        self.stats["pages_requested"] += 1
        cached, cache_meta, stale_refresh = self.cache_lookup(url, force_refresh=force_refresh)

        if stale_refresh:
            self.stats["pages_stale_refreshed"] += 1
            self.emit(
                f"Refreshing stale page ({cache_meta.get('age_hours', 0):.1f}h old): {url}",
                stats=dict(self.stats),
            )

        if cached is not None and self.cached_container_icons_are_legacy(cached):
            self.emit(
                f"Refreshing legacy container icon metadata: {url}",
                stats=dict(self.stats),
            )
            cached = None

        if cached is not None:
            self.stats["pages_cache_hit"] += 1
            self.emit(
                f"Cache hit: {url}",
                stats=dict(self.stats),
            )
            return cached

        self.open_rendered(page, url)
        self.stats["pages_downloaded"] += 1
        self.trigger_lazy_sections(page)
        loc = page.locator("table")
        raw = []

        for i in range(loc.count()):
            t = self.parse_table(loc.nth(i), i)
            if t["headers"]:
                raw.append(t)

        acq, contents, other = self.analyze_tables_for_page(url, raw)
        payload = {
            "url": clean_url(url),
            "identity_url": identity_url(url),
            "title": page.title() or "",
            "icon_url": self.page_item_icon(page),
            "acquisition": acq,
            "container_contents": contents,
            "other_relationships": other,
        }
        self.cache.put(url, payload)
        self.emit(
            f"Scanned page: {url}",
            stats=dict(self.stats),
        )
        return payload

    def primary_recipe_links(self, page_record):
        """Return normal equipment recipes for the current target item.

        Core-conversion recipes are excluded when a normal recipe exists because
        the planner treats the normal equipment craft as the primary acquisition cost.
        """
        craft = next(
            (rel for rel in page_record.get("acquisition", []) if rel.get("kind") == "Craftable From"),
            None,
        )
        if not craft:
            return []

        rows = list(craft.get("rows", []))
        normal_rows = []
        for row in rows:
            c = self.cell(row, "Name")
            urls = [
                clean_url(l.get("url", ""))
                for l in (c or {}).get("links", [])
                if "/db/recipe/" in (l.get("url", "") or "")
            ]
            if any("_core" not in u.lower() for u in urls):
                normal_rows.append(row)

        if normal_rows:
            rows = normal_rows

        out = []
        seen = set()

        for row in rows:
            c = self.cell(row, "Name")
            if not c:
                continue

            for l in c.get("links", []):
                url = clean_url(l.get("url", ""))
                if "/db/recipe/" not in url:
                    continue
                if "_core" in url.lower() and normal_rows:
                    continue

                key = identity_url(url)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "recipe_url": url,
                        "recipe_name": (l.get("text") or row.get("Name") or "").strip(),
                    }
                )

        return out

    def scrape_recipe_cost(self, page, recipe_url, recipe_name="", force_refresh=False):
        """Read Questlog's Gold Cost from one terminal recipe page."""
        self.check_cancel()
        self.stats["pages_requested"] += 1

        cached, cache_meta, stale_refresh = self.cache_lookup(recipe_url, force_refresh=force_refresh)
        if stale_refresh:
            self.stats["pages_stale_refreshed"] += 1
            self.emit(
                f"Refreshing stale recipe ({cache_meta.get('age_hours', 0):.1f}h old): {recipe_name or recipe_url}",
                stats=dict(self.stats),
            )

        if cached is not None and cached.get("record_type") == "recipe_cost":
            self.stats["pages_cache_hit"] += 1
            self.emit(
                f"Recipe cost cache hit: {recipe_name or recipe_url}",
                stats=dict(self.stats),
            )
            return cached

        self.open_rendered(page, recipe_url)
        self.stats["pages_downloaded"] += 1

        try:
            body = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body = ""

        match = re.search(r"Gold\s+Cost:\s*([0-9][0-9,\.]*)", body, re.I)
        cost = None
        raw_cost = None

        if match:
            raw_cost = match.group(1).strip()
            digits = re.sub(r"[^0-9]", "", raw_cost)
            if digits:
                try:
                    cost = int(digits)
                except ValueError:
                    cost = None

        payload = {
            "record_type": "recipe_cost",
            "recipe_url": clean_url(recipe_url),
            "recipe_name": recipe_name,
            "title": page.title() or "",
            "sollant_cost": cost,
            "raw_gold_cost": raw_cost,
        }
        self.cache.put(recipe_url, payload)
        self.emit(
            f"Read crafting cost: {recipe_name or recipe_url}",
            stats=dict(self.stats),
        )
        return payload

    def child_item_links(self, page_record):
        out = []

        for rel in page_record["acquisition"]:
            kind = rel["kind"]

            for r in rel["rows"]:
                if kind == "Craftable From":
                    c = self.cell(r, "Materials")
                    if c:
                        for l in c.get("links", []):
                            u = clean_url(l.get("url", ""))
                            if is_db_item(u):
                                out.append({
                                    "url": u,
                                    "edge_kind": "material",
                                    "name": l.get("text", ""),
                                    "amount": l.get("amount"),
                                })

                elif kind == "Containers / Reward Chests":
                    if r["cells"]:
                        for l in r["cells"][0].get("links", []):
                            u = clean_url(l.get("url", ""))
                            if is_db_item(u):
                                out.append({
                                    "url": u,
                                    "edge_kind": "container",
                                    "name": l.get("text", ""),
                                    "amount": None,
                                })

        seen = set()
        deduped = []
        for x in out:
            k = (identity_url(x["url"]), x["edge_kind"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(x)

        return deduped

    def build_graph(self, page, start_url, depth, force_refresh=False):
        nodes = {}
        queue = [(clean_url(start_url), 0)]
        queued = {identity_url(start_url)}

        while queue:
            self.check_cancel()
            url, d = queue.pop(0)
            key = identity_url(url)
            if key in nodes:
                continue

            rec = self.scrape_page(page, url, force_refresh=force_refresh)
            children = self.child_item_links(rec)

            node = {
                **rec,
                "depth": d,
                "children": children,
            }
            nodes[key] = node

            if d < depth:
                for ch in children:
                    ck = identity_url(ch["url"])
                    if ck not in queued:
                        queued.add(ck)
                        queue.append((ch["url"], d + 1))

            if not self.cache.get(url):
                remaining = float(self.config["between_pages_seconds"])
                while remaining > 0:
                    self.check_cancel()
                    step = min(0.2, remaining)
                    time.sleep(step)
                    remaining -= step

        return nodes

    def scan(
        self,
        build_url: str,
        show_browser: bool,
        force_refresh: bool,
        recursive_depth: int,
        stale_after_hours=None,
    ):
        self.stale_after_hours = (
            max(1.0, float(stale_after_hours))
            if stale_after_hours is not None
            else None
        )

        result = {
            "version": 20,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "build_url": build_url,
            "scan_mode": "force" if force_refresh else ("stale" if self.stale_after_hours is not None else "normal"),
            "stale_after_hours": self.stale_after_hours,
            "items": [],
        }

        self.browser_visible = show_browser
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not show_browser)
            context = browser.new_context(
                viewport={"width": 1536, "height": 1100},
                locale="en-US",
            )
            page = context.new_page()

            try:
                discovered = self.discover_build(page, build_url)
                ordered = sorted(discovered.items(), key=lambda kv: kv[1]["slot_index"])

                total = len(ordered)
                for idx, (name, meta) in enumerate(ordered, 1):
                    self.check_cancel()
                    self.emit(
                        f"Scanning {name}",
                        phase="items",
                        current=idx - 1,
                        total=total,
                        current_item=name,
                        stats=dict(self.stats),
                    )

                    target = self.scrape_page(page, meta["url"], force_refresh=force_refresh)
                    graph = self.build_graph(
                        page,
                        meta["url"],
                        depth=recursive_depth,
                        force_refresh=force_refresh,
                    )

                    crafting_recipes = []
                    for recipe_meta in self.primary_recipe_links(target):
                        self.check_cancel()
                        crafting_recipes.append(
                            self.scrape_recipe_cost(
                                page,
                                recipe_meta["recipe_url"],
                                recipe_name=recipe_meta.get("recipe_name", ""),
                                force_refresh=force_refresh,
                            )
                        )

                    result["items"].append({
                        "slot_index": meta["slot_index"],
                        "item_name": name,
                        "item_url": meta["url"],
                        "item_icon_url": meta.get("icon_url"),
                        "acquisition": target["acquisition"],
                        "container_contents": target["container_contents"],
                        "other_relationships": target.get("other_relationships", []),
                        "crafting_recipes": crafting_recipes,
                        "expanded_nodes": graph,
                    })

                    self.emit(
                        f"Finished {name}",
                        phase="items",
                        current=idx,
                        total=total,
                        current_item=name,
                        stats=dict(self.stats),
                    )
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        return result
