import SwiftUI

struct AlertEditorView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @Environment(\.dismiss) private var dismiss

    let ticker: String
    let currentPrice: Double?
    let alert: AlertRule?

    @State private var enabled: Bool
    @State private var metric: AlertMetric
    @State private var alertOperator: AlertOperator
    @State private var threshold: Double
    @State private var weekdays: Set<Int>
    @State private var startDate: Date
    @State private var endDate: Date
    @State private var frequency: Int
    @State private var cooldown: Int

    private var isEditing: Bool {
        alert != nil
    }

    init(ticker: String, currentPrice: Double?, alert: AlertRule? = nil) {
        self.ticker = ticker
        self.currentPrice = currentPrice
        self.alert = alert
        _enabled = State(initialValue: alert?.enabled ?? true)
        _metric = State(initialValue: alert?.metric ?? .price)
        _alertOperator = State(initialValue: alert?.operator ?? .gte)
        _threshold = State(initialValue: alert?.threshold ?? currentPrice ?? 0)
        _weekdays = State(initialValue: Set(alert?.weekdays ?? [1, 2, 3, 4, 5]))
        _startDate = State(initialValue: Self.date(from: alert?.startTime) ?? Self.date(hour: 10, minute: 0))
        _endDate = State(initialValue: Self.date(from: alert?.endTime) ?? Self.date(hour: 18, minute: 0))
        _frequency = State(initialValue: alert?.frequencyMinutes ?? 15)
        _cooldown = State(initialValue: alert?.cooldownMinutes ?? 60)
    }

    var body: some View {
        Form {
            Section {
                Toggle("Enabled", isOn: $enabled)

                Picker("Metric", selection: $metric) {
                    ForEach(AlertMetric.allCases) { metric in
                        Text(metric.label).tag(metric)
                    }
                }
                .pickerStyle(.segmented)

                Picker("Target", selection: $alertOperator) {
                    ForEach(AlertOperator.allCases) { op in
                        Text(op.label).tag(op)
                    }
                }
                .pickerStyle(.segmented)

                TextField(metric == .price ? "BRL" : "Percent", value: $threshold, format: .number)
                    .keyboardType(.decimalPad)
            }

            Section("Week") {
                WeekdayPicker(selected: $weekdays)
            }

            Section("Window") {
                DatePicker("Start", selection: $startDate, displayedComponents: .hourAndMinute)
                DatePicker("End", selection: $endDate, displayedComponents: .hourAndMinute)
                Stepper("Every \(frequency)m", value: $frequency, in: 1...240, step: 5)
                Stepper("Cooldown \(cooldown)m", value: $cooldown, in: 0...1440, step: 15)
            }

            Button {
                Task { await save() }
            } label: {
                Label(isEditing ? "Update" : "Save", systemImage: "checkmark")
            }
            .disabled(weekdays.isEmpty)
        }
        .navigationTitle(isEditing ? "Edit Alert" : ticker)
    }

    private func save() async {
        let baseline = metric == .percent ? alert?.baselinePrice ?? currentPrice ?? alert?.lastPrice : nil
        if let alert {
            let request = AlertRuleUpdateRequest(
                enabled: enabled,
                metric: metric,
                operator: alertOperator,
                threshold: threshold,
                baselinePrice: baseline,
                weekdays: weekdays.sorted(),
                startTime: Self.hhmm(startDate),
                endTime: Self.hhmm(endDate),
                timezone: TimeZone.current.identifier,
                frequencyMinutes: frequency,
                cooldownMinutes: cooldown
            )
            await model.updateAlert(alert, request: request)
            dismiss()
            return
        }

        let request = AlertRuleCreateRequest(
            ticker: ticker,
            metric: metric,
            operator: alertOperator,
            threshold: threshold,
            baselinePrice: baseline,
            weekdays: weekdays.sorted(),
            startTime: Self.hhmm(startDate),
            endTime: Self.hhmm(endDate),
            timezone: TimeZone.current.identifier,
            frequencyMinutes: frequency,
            cooldownMinutes: cooldown,
            enabled: enabled
        )
        await model.createAlert(request)
        dismiss()
    }

    private static func hhmm(_ date: Date) -> String {
        let parts = Calendar.current.dateComponents([.hour, .minute], from: date)
        return String(format: "%02d:%02d", parts.hour ?? 0, parts.minute ?? 0)
    }

    private static func date(hour: Int, minute: Int) -> Date {
        Calendar.current.date(bySettingHour: hour, minute: minute, second: 0, of: Date()) ?? Date()
    }

    private static func date(from value: String?) -> Date? {
        guard let value else { return nil }
        let parts = value.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else {
            return nil
        }
        return date(hour: hour, minute: minute)
    }
}

struct WeekdayPicker: View {
    @Binding var selected: Set<Int>

    private let days = [
        (1, "Mon"),
        (2, "Tue"),
        (3, "Wed"),
        (4, "Thu"),
        (5, "Fri"),
        (6, "Sat"),
        (7, "Sun"),
    ]

    var body: some View {
        ForEach(days, id: \.0) { value, label in
            Toggle(label, isOn: Binding(
                get: { selected.contains(value) },
                set: { isOn in
                    if isOn {
                        selected.insert(value)
                    } else {
                        selected.remove(value)
                    }
                }
            ))
        }
    }
}
