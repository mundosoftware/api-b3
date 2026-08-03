import SwiftUI

struct AlertEditorView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @Environment(\.dismiss) private var dismiss

    let ticker: String
    let currentPrice: Double?

    @State private var metric: AlertMetric = .price
    @State private var alertOperator: AlertOperator = .gte
    @State private var threshold: Double
    @State private var weekdays: Set<Int> = [1, 2, 3, 4, 5]
    @State private var startDate = AlertEditorView.date(hour: 10, minute: 0)
    @State private var endDate = AlertEditorView.date(hour: 18, minute: 0)
    @State private var frequency = 15
    @State private var cooldown = 60

    init(ticker: String, currentPrice: Double?) {
        self.ticker = ticker
        self.currentPrice = currentPrice
        _threshold = State(initialValue: currentPrice ?? 0)
    }

    var body: some View {
        Form {
            Section {
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
                Label("Save", systemImage: "checkmark")
            }
            .disabled(weekdays.isEmpty)
        }
        .navigationTitle(ticker)
    }

    private func save() async {
        let request = AlertRuleCreateRequest(
            ticker: ticker,
            metric: metric,
            operator: alertOperator,
            threshold: threshold,
            baselinePrice: metric == .percent ? currentPrice : nil,
            weekdays: weekdays.sorted(),
            startTime: Self.hhmm(startDate),
            endTime: Self.hhmm(endDate),
            timezone: TimeZone.current.identifier,
            frequencyMinutes: frequency,
            cooldownMinutes: cooldown,
            enabled: true
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
