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

    private var primaryTitle: String {
        if isRecording { return "Stop and inspect · \(clock(elapsedSeconds)) / 0:30" }
        if isWorking { return workingTitle }
        return captureMode == .selectedPortion ? "Select area to record" : "Start recording"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header

            Text("CAPTURE")
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .tracking(1.1)
                .foregroundStyle(.tertiary)
                .padding(.top, 28)

            Text("Choose what to record")
                .font(.system(size: 21, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
                .padding(.top, 5)

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
                Label("Load video or image…", systemImage: "photo.on.rectangle.angled")
                    .font(.system(size: 12, weight: .medium))
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(isWorking || isRecording)

            Spacer(minLength: 0)

            Text("Record up to 30 seconds. Stop whenever you have the interaction.")
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
                .padding(.top, 14)
        }
        .padding(26)
        .frame(width: 440, height: 360)
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
