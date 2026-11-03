# Changelog

## [1.1.0] - 2026-11-03

### Fixed

- Send remote-control key presses to `/web/remotecontrol` instead of `/web/zap`, and parse
  its `e2result`/`e2resulttext` response.
- Correct the Enigma2 key code for play/pause (207) and add play (207) and pause (119).
  Stop remains 128.
- Use the live-TV left/right keys (105/106) for next/previous channel. On DreamOS, the channel
  keys 402/403 open the service list and switch bouquets there; they do not zap channels.
- Make the `standby` setter use the idempotent standby/wakeup commands instead of a raw
  toggle, then refresh the power state and keep the requested state if the refresh fails.
- Report `EpgEvent.duration` and `EpgEvent.remaining` in seconds instead of minutes.
- Read `NetworkInterface.ip6` and `gateway6` from `e2ip6` and `e2gateway6`.

### Added

- `DreamboxApi.play()`, `pause()`, `togglePlayPause()`, `set_channel_up()` and
  `set_channel_down()`. `tooglePlayPause()` remains as a compatibility alias.
- `EpgEvent.duration_minutes` and `EpgEvent.remaining_minutes` for callers that display
  minutes.
- `RemoteControlResult` for `/web/remotecontrol` responses. `set_remotekeypress()` now returns
  this type instead of `SimpleResult`, and `stop()` returns its result.
- `set_powerstate()` now returns the state reported by the webinterface, or `None` when it cannot
  be read. Only `POWER_GET` (`-1`) updates the cached standby state; use `get_powerstate()` for
  an authoritative refresh after a command.
- Request timeouts, typed exceptions (`DreamboxConnectionError`,
  `DreamboxAuthenticationError`, `DreamboxProtocolError`), `close()`, and `update_status()`.
- `get_picon()` returns the authenticated image bytes and content type.
- `get_all_services()` and a cached two-request `get_bouquets()` using `/web/getallservices`.
- `update()` tolerates a failed device-info fetch and continues with status and bouquets.

### Changed

- `EpgEvent.duration` and `EpgEvent.remaining` now return seconds. Callers that display minutes
  should use `duration_minutes` / `remaining_minutes`.
