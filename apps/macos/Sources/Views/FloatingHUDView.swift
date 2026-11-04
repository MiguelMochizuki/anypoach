import SwiftUI
import AVKit

struct HUDPaletteToken: Identifiable {
    let hex: String
    let color: Color
    var id: String { hex }
}

struct FloatingHUDView: View {
    let sourceURL: URL
    let isVideo: Bool
    @State private var player: AVPlayer?
    @State private var comments: [CaptureComment] = []
    @State private var commentsOpen = false
    @State private var playback = CommentPlayback()
    let palette: [HUDPaletteToken]
    var onCopyContext: (String) -> Void
    var onShareContext: (String) throws -> Void
    @State private var connected = false
    @State private var showingAssistantSetup = false
    @State private var shareStatus = ""
    @State private var context = ""
    @State private var copied = false
    @State private var colorOverrides: [String: Color] = [:]
    var onClose: () -> Void

    var body: some View {
        HStack(spacing: 0) {
        ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            header

            if isVideo {
                CaptureVideoPlayer(player: player)
                    .frame(height: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                CommentTimeline(playback: playback, comments: $comments, isOpen: $commentsOpen)
            } else if let image = NSImage(contentsOf: sourceURL) {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fit).frame(maxHeight: 260)
            }

            VStack(alignment: .leading, spacing: 9) {
                Text("Colors").font(.headline)
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
                Text("Instructions").font(.headline)
                TextField("What should your assistant build or change?", text: $context, axis: .vertical)
                    .lineLimit(3...5)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityLabel("Instructions")
                    .onChange(of: context) { copied = false; shareStatus = "Changes have not been shared yet." }
            }

            HStack(spacing: 10) {
            Button("Continue with Codex or Claude") {
                connected = Self.hasLiveConnector()
                guard connected else { return }
                do {
                    try onShareContext(implementationContext)
                    shareStatus = "Brief published locally. In your connected Codex or Claude, ask: Read my Poach brief, describe the interaction, and recreate it in my project."
                } catch {
                    shareStatus = "Could not share: \(error.localizedDescription)"
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!connected)
            if !connected {
                Label {
                    Text("Connect an MCP assistant to continue.")
                        .font(.caption)
                } icon: {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .symbolRenderingMode(.multicolor)
                        .foregroundStyle(.yellow)
                }
                .accessibilityElement(children: .combine)
            }
            }
            Button("Open Settings…") { showingAssistantSetup = true }
                .buttonStyle(.link)
            if !shareStatus.isEmpty {
                Text(shareStatus).font(.caption).foregroundStyle(.secondary)
            }

            HStack(spacing: 9) {
                Button(action: { onCopyContext(implementationContext); copied = true }) {
                    Label(copied ? "Prompt copied" : "Copy Prompt", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(HUDButtonStyle(prominent: false))


            }
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .preferredColorScheme(.light)
        }
        if isVideo && commentsOpen {
            Divider()
            CommentSidebar(playback: playback, comments: $comments, isOpen: $commentsOpen)
                .frame(width: 230)
        }
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
        .frame(width: min(isVideo ? 750 : 550, (NSScreen.main?.visibleFrame.width ?? 800) - 48),
               height: min(615, (NSScreen.main?.visibleFrame.height ?? 800) - 80))
        .sheet(isPresented: $showingAssistantSetup) { AssistantSetupView() }
        .task {
            while !Task.isCancelled {
                connected = Self.hasLiveConnector()
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
            }
        }
        .onAppear {
            if isVideo {
                let newPlayer = AVPlayer(url: sourceURL)
                player = newPlayer
                playback.attach(newPlayer)
            }
        }
        .onChange(of: comments) { copied = false; shareStatus = "Changes have not been shared yet." }
        .onDisappear { playback.detach(); player = nil }
    }

    private static func hasLiveConnector() -> Bool {
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Caches/Poach/connections")
        guard let entries = try? FileManager.default.contentsOfDirectory(at: directory,
                includingPropertiesForKeys: [.contentModificationDateKey]) else { return false }
        return entries.contains { entry in
            guard let pid = Int32(entry.lastPathComponent), pid > 0,
                  let modified = try? entry.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate,
                  Date().timeIntervalSince(modified) < 15 else { return false }
            return kill(pid, 0) == 0
        }
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
        return ([context] + comments.map { String(format: "[%.2fs] %@", $0.time, $0.text) } + replacements).filter { !$0.isEmpty }.joined(separator: "\n")
    }

    private func hex(_ color: Color) -> String {
        guard let rgb = NSColor(color).usingColorSpace(.sRGB) else { return "#000000" }
        return String(format: "#%02X%02X%02X", Int((rgb.redComponent * 255).rounded()),
            Int((rgb.greenComponent * 255).rounded()), Int((rgb.blueComponent * 255).rounded()))
    }

}

private struct CaptureVideoPlayer: NSViewRepresentable {
    let player: AVPlayer?

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .none
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
