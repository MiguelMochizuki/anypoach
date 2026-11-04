import SwiftUI
import UniformTypeIdentifiers

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
    let loadingFile: URL?
    @State private var targeted = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var settings = false

    private var primaryTitle: String {
        if isRecording { return "Stop and inspect · \(clock(elapsedSeconds)) / 0:30" }
        if isWorking { return workingTitle }
        switch captureMode {
        case .selectedPortion: return "Select an area…"
        case .fullScreen: return "Choose a screen…"
        case .window: return "Choose a window…"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                header
                Spacer()
                Picker("Poach", selection: $settings) {
                    Text("Capture").tag(false)
                    Text("Settings").tag(true)
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .fixedSize()
            }
            if settings {
                ScrollView { PoachSettingsView().padding(1) }
            } else {
                captureControls
            }
        }
        .padding(16)
        .frame(width: min(440, (NSScreen.main?.visibleFrame.width ?? 800) - 32),
               height: min(settings ? 380 : 278, (NSScreen.main?.visibleFrame.height ?? 800) - 50),
               alignment: .topLeading)
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
    }

    private var captureControls: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("What do you want to record?").font(.headline)
                Spacer()
                Text("30 s max").font(.caption).foregroundStyle(.secondary)
            }
            Picker("What do you want to record?", selection: $captureMode) {
                ForEach(PoachCaptureMode.allCases) { mode in
                    Text(mode.title).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .disabled(isWorking || isRecording)

            Button(action: isRecording ? onStopRecording : onStartRecording) {
                Label(primaryTitle, systemImage: isRecording ? "stop.circle.fill" : (isWorking ? "hourglass" : "record.circle"))
                    .font(.system(size: 13, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 2)
            }
            .buttonStyle(.borderedProminent)
            .tint(isRecording ? Color.red : Color.accentColor)
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            .disabled(isWorking)


            if let loadingFile {
                HStack(spacing: 12) {
                    Image(systemName: "doc").font(.title2).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(loadingFile.lastPathComponent).font(.headline).lineLimit(1)
                        Text("Inspecting…").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    ProgressView().controlSize(.small)
                }
                .padding(14)
                .background(.black.opacity(0.035), in: RoundedRectangle(cornerRadius: 14))
                .accessibilityElement(children: .combine)
            } else {
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
            .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
                guard !isWorking, !isRecording, providers.count == 1, let file = providers.first else { return false }
                _ = file.loadDataRepresentation(forTypeIdentifier: UTType.fileURL.identifier) { data, _ in
                    guard let data, let url = URL(dataRepresentation: data, relativeTo: nil), url.isFileURL else { return }
                    DispatchQueue.main.async { onDropMedia(url) }
                }
                return true
            }
            .animation(reduceMotion ? nil : .spring(duration: 0.26, bounce: 0.15), value: targeted)
            .disabled(isWorking || isRecording)
            }
        }
        .animation(reduceMotion ? nil : .spring(duration: 0.28, bounce: 0.1), value: loadingFile)
    }

    private var header: some View {
        HStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(LinearGradient(colors: [Color(red: 0.28, green: 0.66, blue: 0.60), Color(red: 0.18, green: 0.43, blue: 0.53)], startPoint: .topLeading, endPoint: .bottomTrailing))
                PoachPouchShape()
                    .stroke(.white, style: StrokeStyle(lineWidth: 1.45, lineCap: .round, lineJoin: .round))
                PoachBagDetails()
                    .stroke(.white.opacity(0.9), style: StrokeStyle(lineWidth: 1.05, lineCap: .round, lineJoin: .round))
                PoachLootPixels().fill(.white)
            }
            .frame(width: 30, height: 30)

            Text("Poach").font(.headline)
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
