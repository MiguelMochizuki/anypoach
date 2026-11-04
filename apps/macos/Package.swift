// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Poach",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "Poach", targets: ["PoachApp"])],
    targets: [
        .executableTarget(
            name: "PoachApp",
            path: "Sources",
            swiftSettings: [.swiftLanguageMode(.v6)]
        )
    ]
)
