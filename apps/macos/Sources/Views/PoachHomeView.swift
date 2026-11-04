import SwiftUI

struct PoachHomeView: View {
    let isWorking: Bool
    var workingTitle: String = "Preparing your capture…"
    let isRecording: Bool
    let elapsedSeconds: Int
    @Binding var captureMode: PoachCaptureMode
    let onStartRecording: () -> Void
    let onStopRecording: () -> Void
    let onLoadMedia: () -> Void

    let onDropMedia: (URL) -> Void
    @State private var targeted = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var settings = false

    private var primaryTitle: String {
        if isRecording { return "Stop and inspect · \(clock(elapsedSeconds)) / 0:30" }
        if isWorking { return workingTitle }
        return captureMode == .selectedPortion ? "Select area to record" : "Start recording"
    }

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 0) {
            header
            Picker("Poach", selection: $settings) {
                Label("Capture", systemImage: "record.circle").tag(false)
                Label("Settings", systemImage: "gearshape").tag(true)
            }
            .pickerStyle(.segmented).labelsHidden().padding(.top, 18)
            if settings {
                PoachSettingsView().padding(.top, 20)
            } else {

            Text("Choose what to record")
                .font(.system(size: 21, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
                .padding(.top, 20)

            Text(captureMode.guidance)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .padding(.top, 4)

            Picker("Capture mode", selection: $captureMode) {
                ForEach(PoachCaptureMode.allCases) { mode in
                    Text(mode.title).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .padding(.top, 16)
            .disabled(isWorking || isRecording)

            Button(action: isRecording ? onStopRecording : onStartRecording) {
                Label(primaryTitle, systemImage: isRecording ? "stop.circle.fill" : (isWorking ? "hourglass" : "record.circle"))
                    .font(.system(size: 13, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 5)
            }
            .buttonStyle(.borderedProminent)
            .tint(isRecording ? Color.red : Color.accentColor)
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            .disabled(isWorking)
            .padding(.top, 18)

            HStack(spacing: 12) {
                Rectangle().fill(.quaternary).frame(height: 1)
                Text("OR").font(.system(size: 9, weight: .semibold)).foregroundStyle(.tertiary)
                Rectangle().fill(.quaternary).frame(height: 1)
            }
            .padding(.vertical, 14)

            Button(action: onLoadMedia) {
                VStack(spacing: 6) {
                    Image(systemName: targeted ? "arrow.down.to.line" : "square.and.arrow.up")
                        .font(.system(size: 17, weight: .medium))
                        .frame(width: 34, height: 34)
                        .background(.black.opacity(0.055), in: RoundedRectangle(cornerRadius: 9))
                        .scaleEffect(targeted && !reduceMotion ? 1.08 : 1)
                    Text(targeted ? "Release to load" : "Drop an image or video")
                        .font(.system(size: 13, weight: .semibold))
                    Text("or click to browse").font(.caption).foregroundStyle(.secondary)
                }
                .padding(12)
                .frame(maxWidth: .infinity)
                .background(targeted ? Color.accentColor.opacity(0.12) : Color.black.opacity(0.035),
                            in: RoundedRectangle(cornerRadius: 14))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .dropDestination(for: URL.self) { urls, _ in
                guard !isWorking, !isRecording, urls.count == 1, let url = urls.first, url.isFileURL else { return false }
                onDropMedia(url)
                return true
            } isTargeted: { targeted = $0 }
            .animation(reduceMotion ? nil : .spring(duration: 0.26, bounce: 0.15), value: targeted)
            .disabled(isWorking || isRecording)

            Text("Record up to 30 seconds. Stop whenever you have the interaction.")
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
                .padding(.top, 14)

            }
        }
        .padding(22)
        }
        .frame(width: min(600, (NSScreen.main?.visibleFrame.width ?? 800) - 32),
               height: min(680, (NSScreen.main?.visibleFrame.height ?? 800) - 50))
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
    }

    private var header: some View {
        HStack(spacing: 13) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(LinearGradient(colors: [Color(red: 0.28, green: 0.66, blue: 0.60), Color(red: 0.18, green: 0.43, blue: 0.53)], startPoint: .topLeading, endPoint: .bottomTrailing))
                PoachPouchShape()
                    .stroke(.white, style: StrokeStyle(lineWidth: 1.45, lineCap: .round, lineJoin: .round))
                PoachBagDetails()
                    .stroke(.white.opacity(0.9), style: StrokeStyle(lineWidth: 1.05, lineCap: .round, lineJoin: .round))
                PoachLootPixels().fill(.white)
            }
            .frame(width: 48, height: 48)

            VStack(alignment: .leading, spacing: 3) {
                Text("Poach")
                    .font(.system(size: 20, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                Text("Interface motion, made tangible.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    private func clock(_ seconds: Int) -> String {
        String(format: "%d:%02d", seconds / 60, seconds % 60)
    }
}

struct PoachRecordingStatusView: View {
    let elapsedSeconds: Int
    let onStop: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Circle().fill(.red).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text("Recording screen")
                    .font(.system(size: 12, weight: .semibold))
                Text("\(String(format: "%d:%02d", elapsedSeconds / 60, elapsedSeconds % 60)) of 0:30 max")
                    .font(.system(size: 10, design: .monospaced).monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 4)
            Button("Stop") { onStop() }
                .buttonStyle(.borderedProminent)
                .tint(.red)
                .controlSize(.small)
                .keyboardShortcut(.defaultAction)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .frame(width: 260)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(.white.opacity(0.7), lineWidth: 0.5)
        }
        .shadow(color: .black.opacity(0.12), radius: 16, x: 0, y: 6)
        .preferredColorScheme(.light)
    }
}
