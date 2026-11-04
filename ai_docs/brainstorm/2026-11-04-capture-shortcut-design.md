# Capture shortcut

The original Poach objective specifies Command–Shift–P to summon selection. Register that chord through Carbon while the app is running; open selected-area capture when idle and stop an active recording. Ignore it during selection, countdown, and analysis using the existing working-state guard.

A local SwiftUI key equivalent would only work while Poach is focused. A general keyboard event monitor would broaden input access unnecessarily. A dedicated Carbon hotkey registration keeps this interaction limited to one chord and uses the existing capture flow.

Keep the registration controller alive with application state. Report registration conflicts in the menu panel and retain the recording buttons. Use exclusive registration so a conflicting registered hotkey produces a failure instead of triggering two applications. No dependency or generalized key logging is needed.

Validation: the Swift debug and packaged builds passed. The user physically pressed Command–Shift–P from another application and confirmed that Poach opened its selection overlay. Stopping via the same physical shortcut has not been separately verified.
