# What AnyPoach records, keeps and sends

AnyPoach treats recordings, screenshots and keyframes as private local data.

| | |
| --- | --- |
| Telemetry, analytics | None. |
| Audio | Never recorded. |
| Keyboard | Never captured. The optional global shortcut registers one chord (`RegisterHotKey` on Windows, `XGrabKey` on X11) and sees no other key. It is off until you turn it on. |
| Pointer | Position and button state only, by polling. No global input hooks. |
| Network | One request, and only when you press **Check for updates…**: a GET of the latest GitHub release, with nothing sent. The Chrome companion talks to `127.0.0.1` only. |
| Briefs | In the per-OS cache directory, owner-only permissions, deleted after 24 hours. |
| Review frames | Small JPEGs held in memory while the panel is open; never written to disk or sent anywhere. |
| Chrome evidence | In memory for 180 s. |
| Favorites | The only thing kept until you delete it. Private folder, strict validation on import. |

Cache locations: `~/Library/Caches/AnyPoach` (macOS), `~/.cache/AnyPoach` (Linux), `%LOCALAPPDATA%\AnyPoach\Cache` (Windows). Set `ANYPOACH_CACHE_DIR` to use another folder.

The full wording, including Windows ACLs and what CI cannot check, is in [CONTRIBUTING.md](../CONTRIBUTING.md#data-handling).
