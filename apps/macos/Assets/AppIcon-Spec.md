# Poach app icon

The master in `PoachIcon.png` shows a matte cocoa pouch on an ivory tile. The belly is round, the dark band defines the neck, and the soft collar rises on the right. The app build scales this master into the Dock and Finder icon sizes. The Capture header uses the application icon.

At 18 points, the menu bar uses two solid lobes with a transparent gap for the cinch. The higher right tip preserves the collar’s direction. Keep the coordinates in `PoachMenuBar.svg` and `PoachMark.swift` in sync.

On macOS 26 the layered source is `Poach.icon`. The pouch retains its cocoa color in the default appearance, while macOS renders the system icon styles from its separate foreground and background. The app uses the compiled catalog for the Dock. Xcode builds compile the source directly. For a Command Line Tools checkout, run the **Compile macOS icon** GitHub workflow, download its `poach-icon` artifact into `outputs/compiled-icon/`, then rebuild. The build checks the source digest before reusing the catalog.
