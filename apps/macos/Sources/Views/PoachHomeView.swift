import SwiftUI
import UniformTypeIdentifiers

struct PoachHomeView: View {
    let icon: NSImage
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
    @ObservedObject var status: InspectionStatus
    @State private var targeted = false
    @State private var hovering = false
    private var highlightDropZone: Bool { (hovering || targeted) && !isWorking && !isRecording }
    @State private var dragEntry = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var settings = false

    private var primaryTitle: String {
        if isRecording { return "Stop and inspect · \(clock(elapsedSeconds)) / 0:30" }
        if isWorking && loadingFile == nil { return workingTitle }
        switch captureMode {
        case .selectedPortion: return "Select an area…"
        case .fullScreen: return "Choose a screen…"
        case .window: return "Choose a window…"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                header
                Spacer()
                PoachSegments(label: "Poach", selection: $settings, choices: [(false, "Capture"), (true, "Settings")], underlined: true)
                    .frame(width: 144)

            }
            Group {
                if settings {
                    PoachSettingsView(captureBusy: isWorking || isRecording)
                } else {
                    captureControls
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.14), value: settings)
        }
        .padding(16)
        .frame(width: min(440, (NSScreen.main?.visibleFrame.width ?? 800) - 32),
               height: 320, alignment: .topLeading)
        .fixedSize(horizontal: false, vertical: true)
        .background(PoachPalette.canvas)
        .tint(PoachPalette.ink)
        .preferredColorScheme(.light)
    }

    private var captureControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("What do you want to record?").font(.headline)
                Spacer()
            }
            .frame(height: 24)
            PoachSegments(label: "What do you want to record?", selection: $captureMode,
                          choices: PoachCaptureMode.allCases.map { ($0, $0.title) })
            .disabled(isWorking || isRecording)

            Button(action: isRecording ? onStopRecording : onStartRecording) {
                Text(primaryTitle).frame(maxWidth: .infinity)
            }
            .buttonStyle(PoachActionStyle(fill: isRecording ? .red : PoachPalette.ink, foreground: .white))
            .keyboardShortcut(.defaultAction)
            .disabled(isWorking)


            if let loadingFile {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "doc").font(.title2).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(loadingFile.lastPathComponent).font(.headline).lineLimit(1)
                        InspectionStatusLabel(status: status)
                    }
                    Spacer()
                }
                .padding(14)
                .background(.black.opacity(0.035), in: RoundedRectangle(cornerRadius: 14))
                .accessibilityElement(children: .contain)
            } else {
            Button(action: onLoadMedia) {
                VStack(spacing: 6) {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 17, weight: .medium))
                        .frame(width: 34, height: 34)
                        .background(PoachPalette.inset, in: RoundedRectangle(cornerRadius: 9))
                        .foregroundStyle(.primary)
                        .keyframeAnimator(initialValue: 0.0, trigger: dragEntry) { [animate = targeted && !reduceMotion] icon, displacement in
                            let offset = animate ? displacement : 0
                            icon.rotationEffect(.degrees(offset * 1.6))
                                .offset(x: offset)
                        } keyframes: { _ in
                            CubicKeyframe(-3.0, duration: 0.045)
                            CubicKeyframe(3.0, duration: 0.065)
                            CubicKeyframe(-1.8, duration: 0.055)
                            CubicKeyframe(0.9, duration: 0.05)
                            CubicKeyframe(0.0, duration: 0.065)
                        }
                    Text("Drop an image or video")
                        .font(.system(size: 13, weight: .semibold))
                    Text("or click to browse").font(.caption).foregroundStyle(.secondary)
                }
                .padding(12)
                .frame(maxWidth: .infinity)
                .frame(minHeight: 99, maxHeight: .infinity)
                .background(PoachPalette.canvas)
                .overlay {
                    RoundedRectangle(cornerRadius: 14)
                        .strokeBorder(highlightDropZone ? PoachPalette.ink : PoachPalette.outline)
                        .allowsHitTesting(false)
                }
                .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: highlightDropZone)
                .contentShape(Rectangle())
            }
            .onHover { hovering = $0 }
            .onDisappear { hovering = false }
            .buttonStyle(.plain)
            .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
                guard !isWorking, !isRecording, providers.count == 1, let file = providers.first else { return false }
                _ = file.loadDataRepresentation(forTypeIdentifier: UTType.fileURL.identifier) { data, _ in
                    guard let data, let url = URL(dataRepresentation: data, relativeTo: nil), url.isFileURL else { return }
                    DispatchQueue.main.async { onDropMedia(url) }
                }
                return true
            }
            .onChange(of: targeted) {
                if targeted && !reduceMotion { dragEntry += 1 }
            }
            .disabled(isWorking || isRecording)
            }
        }
        .animation(reduceMotion ? nil : .spring(duration: 0.28, bounce: 0.1), value: loadingFile)
    }

    private var header: some View {
        HStack(spacing: 8) {
            Image(nsImage: icon)
                .resizable()
                .frame(width: 30, height: 30)
                .accessibilityHidden(true)

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
            Text("Recording screen").font(.system(size: 13, weight: .semibold))
                .accessibilityValue("\(elapsedSeconds) of 30 seconds")
            Spacer(minLength: 4)
            Button("Stop") { onStop() }
                .buttonStyle(PoachActionStyle(fill: .red, foreground: .white))
                .keyboardShortcut(.defaultAction)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .frame(width: 260)
        .background(PoachPalette.panel, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(.white.opacity(0.7), lineWidth: 0.5)
        }
        .shadow(color: .black.opacity(0.12), radius: 16, x: 0, y: 6)
        .tint(PoachPalette.ink)
        .preferredColorScheme(.light)
    }
}
