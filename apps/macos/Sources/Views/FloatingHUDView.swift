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
        HStack(alignment: .top, spacing: 0) {
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
                    .lineLimit(nil)
                    .textFieldStyle(.plain)
                    .padding(9)
                    .background(Color(white: 0.96), in: RoundedRectangle(cornerRadius: 6))
                    .accessibilityLabel("Instructions")
                    .onChange(of: context) { copied = false; shareStatus = "Changes have not been shared yet." }
            }

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
            .buttonStyle(PoachActionStyle(fill: .blue, foreground: .white))
            .disabled(!connected)
            if !connected {
                Button { showingAssistantSetup = true } label: {
                Label {
                    Text("Connect an MCP assistant to continue.")
                        .font(.caption)
                } icon: {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .symbolRenderingMode(.multicolor)
                        .foregroundStyle(.yellow)
                }
                .foregroundStyle(Color(red: 0.46, green: 0.38, blue: 0.10))
                }.buttonStyle(.plain).accessibilityHint("Opens Settings")
            }
            if !shareStatus.isEmpty {
                Text(shareStatus).font(.caption).foregroundStyle(.secondary)
            }

            HStack(spacing: 9) {
                Button(action: { onCopyContext(implementationContext); copied = true }) {
                    Text(copied ? "Prompt copied" : "Copy Prompt")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(PoachActionStyle())


            }
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .preferredColorScheme(.light)
        if isVideo && commentsOpen {
            Divider()
            CommentSidebar(playback: playback, comments: $comments, isOpen: $commentsOpen)
                .frame(width: 230)
        }
        }
        .background(Color.white)
        .preferredColorScheme(.light)
        .frame(width: min(isVideo && commentsOpen ? 830 : 550, (NSScreen.main?.visibleFrame.width ?? 800) - 48))
        .fixedSize(horizontal: false, vertical: true)
        .onGeometryChange(for: CGSize.self) { $0.size } action: { size in
            guard let panel = NSApp.windows.first(where: { $0.title == "Poach — Implementation brief" && $0.isVisible }),
                  panel.contentRect(forFrameRect: panel.frame).size != size else { return }
            panel.setContentSize(size)
            pinToEdge(panel)
        }
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
            .buttonStyle(PoachActionStyle())
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
