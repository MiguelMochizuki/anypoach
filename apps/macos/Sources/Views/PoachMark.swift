import SwiftUI

/// Matches the 18 × 18 menu-bar SVG geometry, including its 10° forward lean.
struct PoachPouchShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: 6.3, y: 5.4))
        path.addCurve(to: CGPoint(x: 8.6, y: 5.9), control1: CGPoint(x: 7, y: 6.05), control2: CGPoint(x: 7.75, y: 6.3))
        path.addCurve(to: CGPoint(x: 9.6, y: 5.25), control1: CGPoint(x: 9, y: 5.7), control2: CGPoint(x: 9.15, y: 5.35))
        path.addCurve(to: CGPoint(x: 10.65, y: 5.9), control1: CGPoint(x: 10, y: 5.3), control2: CGPoint(x: 10.1, y: 5.75))
        path.addCurve(to: CGPoint(x: 12.35, y: 5.2), control1: CGPoint(x: 11.25, y: 6.1), control2: CGPoint(x: 11.8, y: 5.75))
        path.addCurve(to: CGPoint(x: 11.55, y: 7.15), control1: CGPoint(x: 12.2, y: 5.95), control2: CGPoint(x: 11.75, y: 6.55))
        path.addCurve(to: CGPoint(x: 14.95, y: 12), control1: CGPoint(x: 13.9, y: 8), control2: CGPoint(x: 15.15, y: 9.8))
        path.addCurve(to: CGPoint(x: 9, y: 15.85), control1: CGPoint(x: 14.75, y: 14.4), control2: CGPoint(x: 12, y: 15.85))
        path.addCurve(to: CGPoint(x: 2.9, y: 12.15), control1: CGPoint(x: 6, y: 15.85), control2: CGPoint(x: 3.25, y: 14.4))
        path.addCurve(to: CGPoint(x: 6.6, y: 7.1), control1: CGPoint(x: 2.5, y: 9.8), control2: CGPoint(x: 3.75, y: 7.85))
        path.addCurve(to: CGPoint(x: 6.3, y: 5.4), control1: CGPoint(x: 6.65, y: 6.45), control2: CGPoint(x: 6.5, y: 5.95))
        path.closeSubpath()
        return placed(path, in: rect)
    }
}

/// A fine cinch line makes the gathered opening read as fabric, not a glass rim.
struct PoachBagDetails: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: 6.45, y: 6.2))
        path.addCurve(to: CGPoint(x: 9.1, y: 6.36), control1: CGPoint(x: 7.35, y: 6.75), control2: CGPoint(x: 8.35, y: 6.8))
        path.addCurve(to: CGPoint(x: 11.65, y: 6.25), control1: CGPoint(x: 9.75, y: 6), control2: CGPoint(x: 10.75, y: 6.65))
        return placed(path, in: rect)
    }
}

/// Two forward-drifting square glints, kept separate from the pouch stroke.
struct PoachLootPixels: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.addRoundedRect(in: CGRect(x: 13.4, y: 2.25, width: 1.3, height: 1.3), cornerSize: CGSize(width: 0.18, height: 0.18))
        path.addRoundedRect(in: CGRect(x: 15.15, y: 4.12, width: 0.8, height: 0.8), cornerSize: CGSize(width: 0.12, height: 0.12))
        return placed(path, in: rect)
    }
}

private func placed(_ path: Path, in rect: CGRect) -> Path {
    path.applying(CGAffineTransform(translationX: -9, y: -10))
        .applying(CGAffineTransform(rotationAngle: .pi / 18))
        .applying(CGAffineTransform(translationX: 9, y: 10))
        .applying(CGAffineTransform(scaleX: rect.width / 18, y: rect.height / 18))
        .applying(CGAffineTransform(translationX: rect.minX, y: rect.minY))
}
