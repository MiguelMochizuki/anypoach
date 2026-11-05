import SwiftUI

enum PoachPalette {
    static let canvas = Color(white: 0.91)
    static let panel = Color(white: 0.96)
    static let inset = Color(white: 0.85)
    static let ink = Color(white: 0.17)
}

struct PoachSegments<Value: Hashable>: View {
    @Namespace private var indicator
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let label: String
    @Binding var selection: Value
    let choices: [(Value, String)]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(choices, id: \.0) { value, title in
                Button {
                    selection = value
                } label: {
                    Text(title)
                        .font(.system(size: 12, weight: selection == value ? .semibold : .regular))
                        .foregroundStyle(selection == value ? Color.white : .primary)
                        .frame(maxWidth: .infinity, minHeight: 22)
                        .background {
                            if selection == value {
                                RoundedRectangle(cornerRadius: 5)
                                    .fill(PoachPalette.ink)
                                    .matchedGeometryEffect(id: "selection", in: indicator)
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selection == value ? .isSelected : [])
            }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.18), value: selection)
        .padding(1)
        .background(PoachPalette.inset, in: RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(label)
    }
}

struct PoachActionStyle: ButtonStyle {
    var fill = PoachPalette.inset
    var foreground = Color.primary
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(enabled ? foreground : Color.secondary)
            .padding(.horizontal, 10)
            .frame(height: 32)
            .background(enabled ? fill : Color(white: 0.85), in: RoundedRectangle(cornerRadius: 9))
            .opacity(configuration.isPressed ? 0.78 : 1)
    }
}

struct PoachCountdown: View {
    let count: Int

    var body: some View {
        Text("\(count)")
            .font(.system(size: 56, weight: .semibold).monospacedDigit())
            .foregroundStyle(.white)
            .contentTransition(.numericText())
            .frame(width: 120, height: 120)
            .background(Color(white: 0.22), in: Circle())
            .overlay { Circle().strokeBorder(.red, lineWidth: 4) }
            .accessibilityLabel("Recording starts in \(count) seconds")
    }
}
