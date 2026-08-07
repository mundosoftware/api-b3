import SwiftUI

struct AlertEditorView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var language: AppLanguage
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
            Toggle(language.text("label.enabled"), isOn: Binding(
                get: { enabled },
                set: { newValue in
                    enabled = newValue
                    guard let alert else { return }
                    Task {
                        await model.updateAlertEnabled(alert, enabled: newValue)
                    }
                }
            ))

            Picker(language.text("label.metric"), selection: $metric) {
                ForEach(AlertMetric.allCases) { metric in
                    Text(metric.label).tag(metric)
                }
            }

            Picker(language.text("label.target"), selection: $alertOperator) {
                ForEach(AlertOperator.allCases) { op in
                    Text(op.label).tag(op)
                }
            }

            TextField(
                metric == .price ? language.text("label.brl") : language.text("label.percent"),
                value: $threshold,
                format: .number
            )

            Section(language.text("section.week")) {
                WeekdayPicker(selected: $weekdays)
            }

            DatePicker(language.text("label.start"), selection: $startDate, displayedComponents: .hourAndMinute)
            DatePicker(language.text("label.end"), selection: $endDate, displayedComponents: .hourAndMinute)

            Stepper(language.everyMinutes(frequency), value: $frequency, in: 1...240, step: 5)
            Stepper(language.cooldownMinutes(cooldown), value: $cooldown, in: 0...1440, step: 15)

            Button {
                Task { await save() }
            } label: {
                Label(
                    isEditing ? language.text("action.update") : language.text("action.save"),
                    systemImage: "checkmark"
                )
            }
            .disabled(weekdays.isEmpty)
        }
        .navigationTitle(isEditing ? language.text("title.edit_alert") : ticker)
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
    @EnvironmentObject private var language: AppLanguage

    @Binding var selected: Set<Int>

    var body: some View {
        ForEach(1...7, id: \.self) { day in
            Toggle(language.text("weekday.\(day)"), isOn: Binding(
                get: { selected.contains(day) },
                set: { isOn in
                    if isOn {
                        selected.insert(day)
                    } else {
                        selected.remove(day)
                    }
                }
            ))
        }
    }
}
