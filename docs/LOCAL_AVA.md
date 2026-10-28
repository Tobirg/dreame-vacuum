# Local AVA adapter (experimental)

This fork adds "Local AVA Agent (root)" without modifying existing Dreame,
MOVA, Trouver or Xiaomi cloud flows. No Dreame account or region is required.
The robot must run a separate local HTTP agent; this repository does not
install or modify that agent.

## Agent HTTP contract

Configure the Home Assistant integration with the full origin, e.g.
http://192.168.2.11:8080, and an optional API token. The adapter uses
Authorization: Bearer TOKEN and does not follow HTTP redirects.

- GET /api/info: JSON object containing model ("dreame.vacuum.r2505"),
  mac (e.g. "AA:BB:CC:DD:EE:FF"), and optionally did, fw_ver, name, netif.
- POST /api/rpc: JSON object with method, params, and optional did.
  The agent must allowlist only get_properties, set_properties, and action.
  It should invoke the robot's AVA msg_cvt handler and return its response
  as JSON with a top-level "result" field. Preserve property-level code,
  siid, piid and value. Missing did in property replies is reconstructed
  by the adapter from the matching request entry.
- Optional GET /api/maps?name=OBJECT: raw map-object data in the original
  Dreame format, not PNG/JPEG or arbitrary user-controlled filesystem paths.
- Optional GET /api/maps/device-file?filename=NAME&type=TYPE: original
  binary payload for local photos, where available.

The API paths above describe an **interface that must be implemented in the
separate robot agent**. They are not known to be present on X50 already.
No generic shell or file traversal access should ever be exposed.
Bind the agent to a trusted network and enforce access control.

## What works and what remains experimental

The transport forwards get_properties, set_properties and action to AVA and
retains Home Assistant polling. It does not emulate MQTT and cannot supply
cloud-only cleaning history, remote backup or events. Before the agent has a
local source for original map files, the maps and map editing cannot work.
On r2505 the availability and format of those files require device tests.

## Free map editing backend

The open integration already contains the map editor operations and exposes
them as Home Assistant services, independent of any premium dashboard card.
Once locally acquired map data is working, these services can be called from
the Developer Tools > Actions UI. Example service data (values are examples,
use the coordinates from your own map; empty lists REPLACE existing zones):

~~~yaml
action: dreame_vacuum.vacuum_set_restricted_zone
target:
  entity_id: vacuum.dreame_x50
data:
  walls:
    - [1200, 1500, 1400, 1500]
  zones: []
  no_mops: []
~~~

~~~yaml
action: dreame_vacuum.vacuum_set_threshold
target:
  entity_id: vacuum.dreame_x50
data:
  passable_thresholds: []
  impassable_thresholds: []
  ramps: []
~~~

The premium Dreame Vacuum Card is an independently licensed proprietary
frontend. This branch deliberately does NOT modify licensing or include
premium code. For a free visualization, use a compatible open-source
Lovelace map card and these exposed services. A full interactive free map
editor UI is not implemented here.

## Tests

From repository root, with requests installed:
python -m unittest discover -s tests -p 'test_local_ava.py'
Tests use a mocked agent and do not touch a real vacuum.
