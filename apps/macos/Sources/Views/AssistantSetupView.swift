import SwiftUI
import AppKit

struct AssistantSetupView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var assistant = "Codex"
    @State private var copied = false

    private var serverPath: String? {
        guard let path = Bundle.main.object(forInfoDictionaryKey: "POACHMCPServerPath") as? String,
              FileManager.default.fileExists(atPath: path) else { return nil }
        return path
    }

    private var configuration: String? {
        guard let serverPath else { return nil }
        let node = Bundle.main.object(forInfoDictionaryKey: "POACHNodePath") as? String ?? "node"
        let runtimePath = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        if assistant == "Codex" {
            return "codex mcp add poach --env PATH=\(quote(runtimePath)) -- \(quote(node)) \(quote(serverPath))"
        }
        let config: [String: Any] = ["mcpServers": ["poach": ["command": node, "args": [serverPath], "env": ["PATH": runtimePath]]]]
        guard let data = try? JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]) else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Connect your assistant").font(.title2.bold())
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text("Set up once, then share captures with the assistant you already use. No API key is needed.")
                .foregroundStyle(.secondary)
            Picker("Assistant", selection: $assistant) {
                Text("Codex").tag("Codex")
                Text("Claude Desktop").tag("Claude Desktop")
            }
            .pickerStyle(.segmented)
            .onChange(of: assistant) { copied = false }
            if let configuration {
                Text(assistant == "Codex"
                     ? "Run this command in Terminal with the Codex CLI installed, then reload your Codex connection."
                     : "In Claude Desktop, open Settings → Developer → Edit Config. Merge this poach entry into mcpServers, keeping your other servers, then restart Claude.")
                    .fixedSize(horizontal: false, vertical: true)
                ScrollView {
                    Text(configuration).font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                }
                .frame(height: 180)
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                Button(copied ? "Copied" : assistant == "Codex" ? "Copy setup command" : "Copy configuration") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(configuration, forType: .string)
                    copied = true
                }
                .buttonStyle(.borderedProminent)
            } else {
                Text("The local assistant server is missing. Rebuild Poach from its project folder with scripts/build-macos-app.sh, then reopen it.")
                    .foregroundStyle(.secondary)
            }
            Divider()
            Text("After connecting").font(.headline)
            Text("Choose Continue with Codex or Claude in your brief, then ask your assistant: “Read my Poach brief, describe the interaction, and recreate it in my project.”")
                .fixedSize(horizontal: false, vertical: true)
            Text("The assistant receives your shared notes and reference images when it reads the brief. This development setup needs the Poach project folder to stay in place.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(width: 560)
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
    }

    private func quote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }
}
