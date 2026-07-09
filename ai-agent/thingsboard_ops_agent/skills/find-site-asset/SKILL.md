---
name: find-site-asset
description: Resolve a building, site, plant, warehouse, or facility name to its ThingsBoard asset id. Use whenever the user refers to a physical location by name and you need the underlying ASSET entity before doing anything else with it (this is never a device).
---

# Find Site Asset

Goal: turn a name like "Warehouse 3" or "Rabat Plant" into a confirmed ThingsBoard
asset id of entity type ASSET.

## Steps

1. If the user gave what looks like an exact, unique asset name, call
   `assets_agent` and ask it to look up the tenant asset by that exact name
   (tool: `getTenantAsset`). Asset names are unique per tenant, same idea as
   device name lookup.

2. Name search is substring-matched against the asset's `name` field only —
   NOT its `label`. Users describe assets by their human-readable label
   (e.g. "building 1"), which often differs from the stored name (e.g.
   "building_1"). So:
   a. Try the literal phrase first (`getTenantAsset` exact match, or
      `getTenantAssets(textSearch=...)`).
   b. If that returns nothing, retry with normalized variants: spaces
      replaced by underscores, spaces replaced by hyphens, and spaces
      removed entirely.
   c. If still nothing, call `getTenantAssets` with no `textSearch` (or a
      broad `type` filter) and scan the returned list yourself, matching
      the user's phrase against each asset's `label` field, not just `name`.

3. If more than one asset matches, list the candidates (name, type, id) and
   ask the user to disambiguate rather than guessing.

4. Once you have exactly one match, confirm and return:
   - asset id (entity type ASSET)
   - asset name
   - asset type

   Never hand back a device id here — if `assets_agent` returns nothing but a
   device with that name exists, tell the user this name belongs to a device,
   not a site/building asset.

This asset id is the required input for the `find-devices-in-site` skill.
