import SwiftUI
import AVFoundation

struct CaptureComment: Identifiable, Equatable {
    let id = UUID()
    let time: Double
    let text: String
}

private func timestamp(_ seconds: Double) -> String {
    String(format: "%d:%05.2f", Int(seconds) / 60, seconds.truncatingRemainder(dividingBy: 60))
}

@Observable @MainActor
final class CommentPlayback {
    private(set) var time = 0.0
    private(set) var duration = 0.0
    private(set) var playing = false
    var highlighted: CaptureComment?
    private var player: AVPlayer?
    private var observer: Any?
    private var expiry: Task<Void, Never>?

    func attach(_ player: AVPlayer) {
        detach()
        self.player = player
        observer = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 0.08, preferredTimescale: 600), queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.refresh() }
        }
    }

    private func refresh() {
        guard let player else { return }
        let length = player.currentItem?.duration.seconds ?? 0
        duration = length.isFinite ? max(0, length) : 0
        let position = player.currentTime().seconds
        time = position.isFinite ? max(0, position) : 0
        playing = player.rate != 0
    }

    func pause() { player?.pause(); refresh() }

    func toggle() {
        if playing { pause(); return }
        if duration > 0 && time >= duration - 0.02 { seek(0) }
        player?.play()
        refresh()
    }

    func seek(_ seconds: Double) {
        time = max(0, min(duration, seconds))
        player?.seek(to: CMTime(seconds: time, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }

    func highlight(_ comment: CaptureComment) {
        expiry?.cancel()
        highlighted = comment
        expiry = Task {
            do { try await Task.sleep(for: .seconds(3)) } catch { return }
            highlighted = nil
        }
    }

    func visit(_ comment: CaptureComment) {
        pause()
        seek(comment.time)
        highlight(comment)
    }

    func detach() {
        expiry?.cancel()
        if let observer { player?.removeTimeObserver(observer) }
        player?.pause()
        observer = nil
        player = nil
    }
}

struct CommentTimeline: View {
    let playback: CommentPlayback
    @Binding var comments: [CaptureComment]
    @Binding var isOpen: Bool

    var body: some View {
        HStack(spacing: 10) {
            Button { playback.toggle() } label: {
                Image(systemName: playback.playing ? "pause.fill" : "play.fill").frame(width: 20)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(playback.playing ? "Pause" : "Play")
            VStack(spacing: 0) {
                Slider(value: Binding(get: { playback.time }, set: { playback.seek($0) }),
                       in: 0...max(playback.duration, 0.01))
                    .accessibilityLabel("Video timeline")
                    .accessibilityValue(timestamp(playback.time))
                GeometryReader { geometry in
                    ForEach(comments) { comment in
                        Button {
                            isOpen = true
                            playback.visit(comment)
                        } label: {
                            Image(systemName: "bubble.left.fill").font(.caption2).foregroundStyle(Color.accentColor)
                                .frame(width: 18, height: 18)
                        }
                        .buttonStyle(.plain)
                        .position(x: markerX(comment, width: geometry.size.width), y: 9)
                        .accessibilityLabel("Comment at \(timestamp(comment.time)): \(comment.text)")
                    }
                    if let comment = playback.highlighted {
                        let width = min(200, geometry.size.width)
                        Text(comment.text).font(.caption).lineLimit(2)
                            .padding(6).frame(width: width)
                            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 7))
                            .position(x: min(max(width / 2, markerX(comment, width: geometry.size.width)), geometry.size.width - width / 2), y: -32)
                            .allowsHitTesting(false)
                    }
                }.frame(height: comments.isEmpty ? 0 : 18)
            }
            Text(timestamp(playback.time)).font(.caption.monospacedDigit())
            Button {
                isOpen.toggle()
                if isOpen { playback.pause() }
            } label: {
                Image(systemName: isOpen ? "circle.inset.filled" : "circle")
                    .font(.system(size: 22))
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.plain)
            .help(isOpen ? "Hide comments" : "Show comments")
            .accessibilityLabel(isOpen ? "Hide comments" : "Show comments")
        }
    }

    private func markerX(_ comment: CaptureComment, width: CGFloat) -> CGFloat {
        9 + max(0, width - 18) * min(1, comment.time / max(0.01, playback.duration))
    }
}

struct CommentSidebar: View {
    let playback: CommentPlayback
    @Binding var comments: [CaptureComment]
    @Binding var isOpen: Bool
    @State private var draft = ""
    @State private var anchor: Double?
    @FocusState private var composing: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Comments").font(.headline)
                Spacer()
                Button { isOpen = false } label: { Image(systemName: "sidebar.right") }
                    .buttonStyle(.plain).accessibilityLabel("Close comments")
            }
            Divider()
                VStack(alignment: .leading, spacing: 14) {
                    if comments.isEmpty { Text("Comments you add appear here.").foregroundStyle(.secondary) }
                    ForEach(comments) { comment in
                        Button { playback.visit(comment) } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(timestamp(comment.time)).font(.caption.monospacedDigit()).foregroundStyle(.tint)
                                Text(comment.text).frame(maxWidth: .infinity, alignment: .leading)
                            }.contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            Divider()
            Text("Comment at \(timestamp(anchor ?? playback.time))").font(.caption.monospacedDigit())
            TextField("Write a comment…", text: $draft, axis: .vertical)
                .textFieldStyle(.roundedBorder).lineLimit(nil).focused($composing)
                .onChange(of: composing) {
                    if composing && draft.isEmpty { playback.pause(); anchor = playback.time }
                }
                .onChange(of: draft) {
                    if draft.isEmpty { anchor = nil }
                    else if anchor == nil { playback.pause(); anchor = playback.time }
                }
            Button("Post comment") {
                let comment = CaptureComment(time: anchor ?? playback.time, text: draft.trimmingCharacters(in: .whitespacesAndNewlines))
                comments.insert(comment, at: comments.firstIndex { $0.time > comment.time } ?? comments.endIndex)
                playback.visit(comment)
                draft = ""
                anchor = nil
            }
            .buttonStyle(.borderedProminent)
            .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(16)
        .background(Color(nsColor: .controlBackgroundColor))
    }
}
