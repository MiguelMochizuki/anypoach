import Foundation

struct PoachInspection: Codable {
    let mediaType: String
    let sourcePath: String
    let durationMs: Int
    let keyframes: [PoachKeyframe]
    let palette: [String]
    let timing: PoachTiming
}

struct PoachKeyframe: Codable {
    let kind: String
    let timeMs: Int
    let imagePath: String
}

struct PoachTiming: Codable {
    let durationMs: Int
    let bezier: [Double]?
    let token: String
}

enum PoachInspectionError: LocalizedError {
    case projectNotBuilt
    case nodeNotFound
    case processFailed(String)

    var errorDescription: String? {
        switch self {
        case .projectNotBuilt:
            "Reinstall Poach to restore its analysis engine."
        case .nodeNotFound:
            "Node.js wasn't found on PATH. Install Node.js 20 or newer, then launch Poach again."
        case .processFailed(let message):
            message
        }
    }
}

enum PoachInspectionRunner {
    static func inspect(videoURL: URL, isRecording: Bool = false,
                        onProgress: @escaping @MainActor @Sendable (String) -> Void) async throws -> PoachInspection {
        guard let engine = findEngine() else { throw PoachInspectionError.projectNotBuilt }
        guard let node = findNode() else { throw PoachInspectionError.nodeNotFound }
        let entry = engine.path
        let videoPath = videoURL.path

        return try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = node
            process.arguments = [
                "--input-type=module", "-e",
                "import { inspectImage, inspectVideo, inspectRecording } from \(Self.jsString(entry)); const inspect = /\\.(png|jpe?g|webp|tiff?|bmp)$/i.test(process.argv[1]) ? inspectImage : (process.argv[2] === 'recording' ? inspectRecording : inspectVideo); try { const result = await inspect(process.argv[1], { onProgress: stage => console.log(stage) }); process.stdout.write(JSON.stringify(result)); } catch (error) { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 1; }",
                videoPath, isRecording ? "recording" : "import",
            ]
            // Node resolves cwd during bootstrap. A checkout under Documents can
            // block there on macOS privacy checks before our script even starts.
            // All inputs and imports are absolute, so no project cwd is needed.
            process.currentDirectoryURL = FileManager.default.temporaryDirectory
            var environment = ProcessInfo.processInfo.environment
            let bundledPath = environment["PATH", default: ""]
            environment["PATH"] = [bundledPath, "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"].joined(separator: ":")
            process.environment = environment
            let output = Pipe()
            let errors = Pipe()
            process.standardOutput = output
            process.standardError = errors
            do {
                try process.run()
                var data = Data()
                for try await line in output.fileHandleForReading.bytes.lines {
                    switch line {
                    case "motion": await onProgress("Finding movement…")
                    case "frames": await onProgress("Preparing preview images…")
                    case "palette": await onProgress("Sampling colors…")
                    default: data.append(contentsOf: line.utf8)
                    }
                }
                process.waitUntilExit()
                guard process.terminationStatus == 0 else {
                    let details = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    throw PoachInspectionError.processFailed(details?.isEmpty == false ? details! : "The analysis process exited with status \(process.terminationStatus). Check that ffmpeg and ffprobe are available.")
                }
                do {
                    return try JSONDecoder().decode(PoachInspection.self, from: data)
                } catch {
                    throw PoachInspectionError.processFailed("Poach returned an unreadable analysis result: \(error.localizedDescription)")
                }
            } catch let error as PoachInspectionError {
                throw error
            } catch {
                throw PoachInspectionError.processFailed("Poach couldn't start its analysis engine: \(error.localizedDescription)")
            }
        }.value
    }

    private static func findEngine() -> URL? {
        if let bundled = Bundle.main.resourceURL?.appending(path: "core/dist/index.js"),
           FileManager.default.fileExists(atPath: bundled.path) {
            return bundled
        }
        return nil
    }

    static func findNode() -> URL? {
        let environmentPaths = ProcessInfo.processInfo.environment["PATH", default: ""].split(separator: ":")
        let paths = environmentPaths + ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
        return paths.lazy.map { URL(fileURLWithPath: String($0)).appending(path: "node") }
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    private static func jsString(_ value: String) -> String {
        let data = try! JSONEncoder().encode(value)
        return String(decoding: data, as: UTF8.self)
    }
}
