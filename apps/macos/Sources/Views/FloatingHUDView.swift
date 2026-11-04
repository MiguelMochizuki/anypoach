import SwiftUI

struct HUDKeyframe: Identifiable {
    let id: Int
    let time: String
    let image: NSImage?
}

struct HUDPaletteToken: Identifiable {
    let hex: String
    let color: Color
    var id: String { hex }
}

struct FloatingHUDView: View {
    let timingToken: String
    let palette: [HUDPaletteToken]
    let keyframes: [HUDKeyframe]
    var onCopyContext: (String) -> Void
    var onShareContext: (String) throws -> Void
    @State private var shareStatus = ""
    @State private var context = ""
    @State private var copied = false
    @State private var colorOverrides: [String: Color] = [:]
    var onPreviewInCursor: () -> Void
    var onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            header

            VStack(alignment: .leading, spacing: 9) {
                sectionLabel("MOTION")
                HStack(spacing: 8) {
                    Image(systemName: "waveform.path")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.tint)
                    Text(timingToken)
                        .font(.system(size: 13, weight: .medium, design: .rounded).monospacedDigit())
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
                .padding(.horizontal, 11)
                .padding(.vertical, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(.primary.opacity(0.055), lineWidth: 0.5)
                }
            }

            VStack(alignment: .leading, spacing: 9) {
                sectionLabel("KEYFRAMES")
                HStack(spacing: 7) {
                    ForEach(keyframes) { frame in
                        VStack(alignment: .leading, spacing: 5) {
                            Group {
                                if let image = frame.image {
                                    Image(nsImage: image).resizable().aspectRatio(contentMode: .fill)
                                } else {
                                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                                        .fill(.primary.opacity(0.06))
                                        .overlay { Image(systemName: "viewfinder").foregroundStyle(.secondary) }
                                }
                            }
                            .frame(height: 48)
                            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                            Text(frame.time)
                                .font(.system(size: 10, weight: .medium, design: .rounded).monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 9) {
                sectionLabel("PALETTE")
                HStack(spacing: 7) {
                    ForEach(palette) { token in
                        VStack(alignment: .leading, spacing: 5) {
                            ColorPicker("Replace \(token.hex)", selection: Binding(
                                get: { colorOverrides[token.hex] ?? token.color },
                                set: { colorOverrides[token.hex] = $0; copied = false; shareStatus = "Changes have not been shared yet." }
                            ), supportsOpacity: false)
                            .labelsHidden()
                            Text(hex(colorOverrides[token.hex] ?? token.color))
                                .font(.system(size: 8, weight: .medium, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .frame(maxWidth: .infinity)
                        .accessibilityElement(children: .contain)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 9) {
                sectionLabel("IMPLEMENTATION CONTEXT")
                TextField("Describe the behavior, framework, or changes…", text: $context, axis: .vertical)
                    .lineLimit(3...5)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityLabel("Implementation context")
                    .onChange(of: context) { copied = false; shareStatus = "Changes have not been shared yet." }
            }

            Button("Share with assistant via MCP") {
                do {
                    try onShareContext(implementationContext)
                    shareStatus = "Shared. Ask your connected assistant to read the Poach brief."
                } catch {
                    shareStatus = "Could not share: \(error.localizedDescription)"
                }
            }
            .buttonStyle(.bordered)
            if !shareStatus.isEmpty {
                Text(shareStatus).font(.caption).foregroundStyle(.secondary)
            }

            HStack(spacing: 9) {
                Button(action: { onCopyContext(implementationContext); copied = true }) {
                    Label(copied ? "Prompt copied" : "Copy Prompt", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(HUDButtonStyle(prominent: true))
                .keyboardShortcut(.defaultAction)

                Button(action: onPreviewInCursor) {
                    Image(systemName: "arrow.up.right.square")
                        .frame(width: 34, height: 30)
                }
                .buttonStyle(HUDButtonStyle(prominent: false))
                .help("Show keyframes in Finder")
                .accessibilityLabel("Show keyframes in Finder")
            }
        }
        .padding(18)
        .frame(width: 340)
        .background {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay {
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .strokeBorder(.white.opacity(0.15), lineWidth: 0.5)
                }
                .shadow(color: .black.opacity(0.16), radius: 28, x: 0, y: 14)
                .shadow(color: .black.opacity(0.06), radius: 5, x: 0, y: 2)
        }
        .preferredColorScheme(.light)
    }

    private var header: some View {
        HStack(spacing: 11) {
            Image(systemName: "waveform.path.ecg.rectangle")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .background(Color.accentColor.gradient, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text("Motion captured")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                Text("Ready to inspect")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.secondary)
                    .frame(width: 24, height: 24)
                    .background(.primary.opacity(0.06), in: Circle())
            }
            .buttonStyle(.plain)
            .help("Close")
        }
    }

    private var implementationContext: String {
        let replacements = palette.compactMap { token -> String? in
            guard let replacement = colorOverrides[token.hex] else { return nil }
            return "Replace \(token.hex) with \(hex(replacement))."
        }
        return ([context] + replacements).filter { !$0.isEmpty }.joined(separator: "\n")
    }

    private func hex(_ color: Color) -> String {
        guard let rgb = NSColor(color).usingColorSpace(.sRGB) else { return "#000000" }
        return String(format: "#%02X%02X%02X", Int((rgb.redComponent * 255).rounded()),
            Int((rgb.greenComponent * 255).rounded()), Int((rgb.blueComponent * 255).rounded()))
    }

    private func sectionLabel(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 9, weight: .bold, design: .rounded))
            .tracking(1.1)
            .foregroundStyle(.tertiary)
    }
}

private struct HUDButtonStyle: ButtonStyle {
    let prominent: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(prominent ? Color.white : Color.primary)
            .padding(.horizontal, prominent ? 11 : 0)
            .frame(height: 30)
            .background {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(prominent ? Color.accentColor : Color.primary.opacity(0.055))
                    .opacity(configuration.isPressed ? 0.8 : 1)
            }
            .overlay {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(.white.opacity(prominent ? 0.12 : 0.08), lineWidth: 0.5)
            }
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
