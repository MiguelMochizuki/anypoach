# Poach app icon geometry

## Menu bar mark

`PoachMenuBar.svg` is the 18 × 18 source vector. The pouch outline is a single 1.4-unit rounded stroke, rotated 10° clockwise around `(9, 10)`. Its generously rounded, broad belly flows into a narrow, visibly gathered mouth. A fine cinch line and right-swept tie make the top read as tied fabric rather than a cup rim. Two square loot pixels sit above the forward shoulder. `currentColor` keeps the mark compatible with template rendering in both macOS appearances.

The belly uses a paired cubic superellipse approximation. At its bottom join, both segments share a horizontal tangent and equal signed curvature: the control handles are mirrored around the centerline, so the lower silhouette stays optically even under the 10° rotation. The 1.4-unit stroke and 1.3-unit pixel are sized for a crisp 18-point Retina template.

## App icon direction

- Use a rounded-square macOS icon canvas with a deep indigo-to-ink gradient and a centered, warm-white pouch mark.
- Keep the pouch and pixels as separate vector layers so the silhouette remains legible at small sizes.
- Scale the same 18-unit geometry proportionally; use a 1.4-unit outline at the menu-bar size and scale the stroke with the icon for larger exports.
- Keep the pouch's 10° clockwise lean and the loot pixels in the upper-right quadrant across all icon sizes.
- Export a 1024 × 1024 master and generate the platform's required raster sizes from that master. Do not bake a shadow into the menu-bar template.
