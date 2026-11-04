import Carbon
import Foundation
import OSLog

/// Registers only the capture chord; it does not monitor arbitrary keystrokes.
@MainActor
final class PoachHotKey {
    private let logger = Logger(subsystem: "dev.poach.app", category: "HotKey")
    private var hotKey: EventHotKeyRef?
    private var handler: EventHandlerRef?
    private var action: (() -> Void)?

    func register(action: @escaping () -> Void) -> Bool {
        self.action = action
        if hotKey != nil { return true }
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let status = InstallEventHandler(GetApplicationEventTarget(), { _, event, context in
            guard let event, let context else { return OSStatus(eventNotHandledErr) }
            var identifier = EventHotKeyID()
            let result = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &identifier)
            guard result == noErr, identifier.signature == 0x506F6163, identifier.id == 1 else {
                return OSStatus(eventNotHandledErr)
            }
            // Carbon dispatches this application event on the main thread.
            MainActor.assumeIsolated {
                Unmanaged<PoachHotKey>.fromOpaque(context).takeUnretainedValue().action?()
            }
            return noErr
        }, 1, &eventType, Unmanaged.passUnretained(self).toOpaque(), &handler)
        guard status == noErr else {
            logger.error("Hotkey event handler failed: \(status)")
            return false
        }
        let registration = RegisterEventHotKey(UInt32(kVK_ANSI_P), UInt32(cmdKey | shiftKey), EventHotKeyID(signature: 0x506F6163, id: 1), GetApplicationEventTarget(), OptionBits(kEventHotKeyExclusive), &hotKey)
        logger.notice("Capture shortcut registration status: \(registration)")
        if registration != noErr {
            if let handler { RemoveEventHandler(handler) }
            handler = nil
            return false
        }
        return true
    }
}
