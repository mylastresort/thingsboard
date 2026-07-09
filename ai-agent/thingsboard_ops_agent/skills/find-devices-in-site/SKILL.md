---
name: find-devices-in-site
description: Given a building/site/facility name, list every device linked to it in ThingsBoard. Use whenever the user asks things like "what devices are in <site>" or "show me sensors at <building>". Depends on find-site-asset to resolve the asset id first.
---

# Find Devices In Site

Goal: given a site/building name, return the devices attached to that asset.

## Steps

1. Resolve the asset id first. If you don't already have it, run the
   `find-site-asset` skill (or repeat its steps yourself) using `assets_agent`
   / `relations_query_agent` to turn the site name into a confirmed asset id.
   Do not proceed with a guessed id.

2. Query outgoing relations from that asset using `relations_query_agent`:
   - Try `findByFromWithRelationType` with the asset as the "from" entity and
     relation type `"Contains"` — this is ThingsBoard's conventional default
     relation for asset → device containment.
   - If that returns nothing, don't assume there are no devices. Call
     `findInfoByFrom` on the asset first to see what relation types actually
     exist outgoing from it, since relation type names are tenant-configurable
     and may differ ("Manages", "Located At", custom names, etc.). Retry with
     whichever relation type is present.
   - For deeper topologies (site → floor → line → device), use
     `findEntityDataByRelationsQueryFilter` rooted at the asset with direction
     FROM, a relatedEntityType filter of DEVICE, and `maxLevel` > 1 so it
     traverses through intermediate assets instead of only the first hop.

3. From the relation results, collect the "to" entity ids where entity type
   is DEVICE (ignore relations pointing to other assets/customers/etc. unless
   you're deliberately traversing multiple hops per step 2).

4. Fetch full device details for the collected ids via `devices_agent`
   (`getDevicesByIds` for a batch, or `getDeviceById` one at a time).

5. Present the result as a list of device name + id (+ type/label if useful).
   If truly zero devices are linked after checking relation types and depth,
   say so plainly rather than fabricating results.
