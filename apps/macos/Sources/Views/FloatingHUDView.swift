import SwiftUI
import AVKit

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
    let sourceURL: URL
    let isVideo: Bool
    @State private var player: AVPlayer?
    @State private var momentNote = ""
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
        ScrollView {
        VStack(alignment: .leading, spacing: 18) {
            header

            Text("Review the capture, add what matters, then continue with your assistant.")
                .font(.body).foregroundStyle(.secondary)
            if isVideo {
                CaptureVideoPlayer(player: player)
                    .frame(height: 260)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                HStack {
                    TextField("What should happen at this moment?", text: $momentNote)
                        .textFieldStyle(.roundedBorder)
                    Button("Add note at playhead") {
                        player?.pause()
                        let seconds = player?.currentTime().seconds ?? 0
                        let time = seconds.isFinite ? max(0, seconds) : 0
                        context += (context.isEmpty ? "" : "\n") + String(format: "[%.2fs] ", time) + momentNote
                        momentNote = ""
                    }
                    .disabled(momentNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            } else if let image = NSImage(contentsOf: sourceURL) {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fit).frame(maxHeight: 260)
            }

            DisclosureGroup("Reference frames and estimated motion") {
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

            Button("Continue with Codex or Claude") {
                do {
                    try onShareContext(implementationContext)
                    shareStatus = "Ready for your assistant. In Codex or Claude, ask: Read my Poach brief, describe the interaction, and recreate it in my project."
                } catch {
                    shareStatus = "Could not share: \(error.localizedDescription)"
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            Text("Uses your connected assistant. No API key needed. Your notes, colors, and reference frames are available when it reads the brief.")
                .font(.caption).foregroundStyle(.secondary)
            if !shareStatus.isEmpty {
                Text(shareStatus).font(.caption).foregroundStyle(.secondary)
            }

            HStack(spacing: 9) {
                Button(action: { onCopyContext(implementationContext); copied = true }) {
                    Label(copied ? "Prompt copied" : "Copy Prompt", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(HUDButtonStyle(prominent: false))

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
        .frame(maxWidth: .infinity)
        .preferredColorScheme(.light)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
        .frame(width: min(660, (NSScreen.main?.visibleFrame.width ?? 800) - 48),
               height: min(720, (NSScreen.main?.visibleFrame.height ?? 800) - 80))
        .onAppear { if isVideo { player = AVPlayer(url: sourceURL) } }
        .onDisappear { player?.pause(); player = nil }
    }

    private var header: some View {
        HStack(spacing: 11) {
            Image(systemName: "waveform.path.ecg.rectangle")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .background(Color.accentColor.gradient, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text("Review your capture")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                Text("Make a brief for your assistant")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Button("New capture") {
                player?.pause()
                onClose()
            }
            .buttonStyle(.bordered)
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

private struct CaptureVideoPlayer: NSViewRepresentable {
    let player: AVPlayer?

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .inline
        view.videoGravity = .resizeAspect
        view.showsFullScreenToggleButton = false
        view.player = player
        return view
    }

    func updateNSView(_ view: AVPlayerView, context: Context) {
        if view.player !== player { view.player = player }
    }

    static func dismantleNSView(_ view: AVPlayerView, coordinator: ()) {
        view.player?.pause()
        view.player = nil
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
