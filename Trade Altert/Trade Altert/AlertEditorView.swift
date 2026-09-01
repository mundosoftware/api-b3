import SwiftUI

struct AlertEditorView: View {
    @EnvironmentObject private var model: CompanionAppModel
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
    @State private var allowsNegativePercent: Bool
    @State private var thresholdText: String
    @State private var initialSnapshot: AlertEditorSnapshot
    @State private var isSaving = false
    @State private var showDiscardConfirmation = false
    @State private var isFormattingThreshold = false
    @FocusState private var isThresholdFocused: Bool

    private var isEditing: Bool {
        alert != nil
    }

    private var canSave: Bool {
        !weekdays.isEmpty && !isSaving
    }

    private var saveTitle: String {
        isEditing ? language.text("action.update") : language.text("action.save")
    }

    private var normalizedThreshold: Double {
        switch metric {
        case .price:
            return max(threshold, 0)
        case .percent:
            return allowsNegativePercent ? -abs(threshold) : abs(threshold)
        }
    }

    private var percentBaselinePrice: Double? {
        alert?.baselinePrice ?? currentPrice ?? alert?.lastPrice
    }

    private var priceResetValue: Double? {
        currentPrice ?? alert?.lastPrice ?? alert?.baselinePrice
    }

    private var percentTargetPrice: Double? {
        guard let percentBaselinePrice else { return nil }
        return percentBaselinePrice * (1 + normalizedThreshold / 100)
    }

    private var currentSnapshot: AlertEditorSnapshot {
        AlertEditorSnapshot(
            enabled: enabled,
            metric: metric,
            alertOperator: alertOperator,
            threshold: normalizedThreshold,
            weekdays: weekdays.sorted(),
            startTime: Self.hhmm(startDate),
            endTime: Self.hhmm(endDate),
            frequency: frequency,
            cooldown: cooldown
        )
    }

    private var hasUnsavedChanges: Bool {
        guard !isSaving else { return false }
        return isEditing ? currentSnapshot != initialSnapshot : true
    }

    init(ticker: String, currentPrice: Double?, alert: AlertRule? = nil) {
        let initialEnabled = alert?.enabled ?? true
        let initialMetric = alert?.metric ?? .price
        let initialOperator = alert?.operator ?? .gte
        let initialThreshold = alert?.threshold ?? currentPrice ?? 0
        let initialWeekdays = Set(alert?.weekdays ?? [1, 2, 3, 4, 5])
        let initialStartDate = Self.date(from: alert?.startTime) ?? Self.date(hour: 10, minute: 0)
        let initialEndDate = Self.date(from: alert?.endTime) ?? Self.date(hour: 18, minute: 0)
        let initialFrequency = alert?.frequencyMinutes ?? 15
        let initialCooldown = alert?.cooldownMinutes ?? 60
        let initialAllowsNegativePercent = initialMetric == .percent && initialThreshold < 0

        self.ticker = ticker
        self.currentPrice = currentPrice
        self.alert = alert
        _enabled = State(initialValue: initialEnabled)
        _metric = State(initialValue: initialMetric)
        _alertOperator = State(initialValue: initialOperator)
        _threshold = State(initialValue: initialThreshold)
        _weekdays = State(initialValue: initialWeekdays)
        _startDate = State(initialValue: initialStartDate)
        _endDate = State(initialValue: initialEndDate)
        _frequency = State(initialValue: initialFrequency)
        _cooldown = State(initialValue: initialCooldown)
        _allowsNegativePercent = State(initialValue: initialAllowsNegativePercent)
        _thresholdText = State(initialValue: Self.thresholdText(
            initialThreshold,
            metric: initialMetric,
            focused: false
        ))
        _initialSnapshot = State(initialValue: AlertEditorSnapshot(
            enabled: initialEnabled,
            metric: initialMetric,
            alertOperator: initialOperator,
            threshold: initialMetric == .percent && initialAllowsNegativePercent
                ? -abs(initialThreshold)
                : abs(initialThreshold),
            weekdays: initialWeekdays.sorted(),
            startTime: Self.hhmm(initialStartDate),
            endTime: Self.hhmm(initialEndDate),
            frequency: initialFrequency,
            cooldown: initialCooldown
        ))
    }

    var body: some View {
        Form {
            Section {
                Toggle(language.text("label.enabled"), isOn: $enabled)

                Picker(language.text("label.metric"), selection: $metric) {
                    ForEach(AlertMetric.allCases) { metric in
                        Text(metric.label).tag(metric)
                    }
                }
                .pickerStyle(.segmented)

                Picker(language.text("label.target"), selection: $alertOperator) {
                    ForEach(AlertOperator.allCases) { op in
                        Text(op.label).tag(op)
                    }
                }
                .pickerStyle(.segmented)

                thresholdInput

                if metric == .percent {
                    Toggle(language.text("label.negative_percent"), isOn: $allowsNegativePercent)
                    percentTargetSummary
                }
            }

            Section(language.text("section.week")) {
                WeekdayPicker(selected: $weekdays)
            }

            Section(language.text("section.window")) {
                DatePicker(language.text("label.start"), selection: $startDate, displayedComponents: .hourAndMinute)
                DatePicker(language.text("label.end"), selection: $endDate, displayedComponents: .hourAndMinute)
                Stepper(language.everyMinutes(frequency), value: $frequency, in: 1...240, step: 5)
                Stepper(language.cooldownMinutes(cooldown), value: $cooldown, in: 0...1440, step: 15)
            }

            Button {
                startSave()
            } label: {
                Label(saveTitle, systemImage: "checkmark")
            }
            .disabled(!canSave)
        }
        .navigationTitle(isEditing ? language.text("title.edit_alert") : ticker)
        .navigationBarBackButtonHidden(hasUnsavedChanges)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            if hasUnsavedChanges {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        attemptDismiss()
                    } label: {
                        Label(language.text("action.cancel"), systemImage: "chevron.backward")
                    }
                }
            }

            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    startSave()
                } label: {
                    Label(saveTitle, systemImage: "checkmark")
                }
                .fontWeight(.semibold)
                .disabled(!canSave)
            }

            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(language.text("action.done")) {
                    isThresholdFocused = false
                }
            }
        }
        .alert(language.text("alert.unsaved_title"), isPresented: $showDiscardConfirmation) {
            Button(language.text("action.keep_editing"), role: .cancel) {}
            Button(language.text("action.discard"), role: .destructive) {
                dismiss()
            }
        } message: {
            Text(language.text(isEditing ? "alert.unsaved_edit_message" : "alert.unsaved_new_message"))
        }
        .onAppear {
            syncThresholdText(focused: isThresholdFocused)
        }
        .onChange(of: metric) { oldValue, newValue in
            handleMetricChange(from: oldValue, to: newValue)
        }
        .onChange(of: allowsNegativePercent) { _, _ in
            guard metric == .percent else { return }
            threshold = normalizedThreshold
            syncThresholdText(focused: isThresholdFocused)
        }
        .onChange(of: isThresholdFocused) { _, focused in
            syncThresholdText(focused: focused)
        }
        .onChange(of: language.code) { _, _ in
            syncThresholdText(focused: isThresholdFocused)
        }
    }

    @ViewBuilder
    private var thresholdInput: some View {
        if metric == .price {
            HStack {
                TextField(language.text("label.brl"), text: $thresholdText)
                    .keyboardType(.numberPad)
                    .focused($isThresholdFocused)
                    .monospacedDigit()
                    .onChange(of: thresholdText) { _, newValue in
                        normalizeThresholdText(newValue)
                    }

                if priceResetValue != nil {
                    Button(language.text("action.reset")) {
                        resetPriceToBaseline()
                    }
                    .buttonStyle(.borderless)
                }
            }
        } else {
            HStack {
                Text(language.text("label.percent"))
                Spacer()
                if normalizedThreshold < 0 {
                    Text("-")
                        .foregroundStyle(.secondary)
                }
                TextField("0", text: $thresholdText)
                    .keyboardType(.decimalPad)
                    .focused($isThresholdFocused)
                    .multilineTextAlignment(.trailing)
                    .monospacedDigit()
                    .frame(maxWidth: 120)
                    .onChange(of: thresholdText) { _, newValue in
                        normalizeThresholdText(newValue)
                    }
                Text("%")
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var percentTargetSummary: some View {
        if let percentBaselinePrice, let percentTargetPrice {
            LabeledContent(language.text("label.based_on_price")) {
                Text(Self.currencyText(percentBaselinePrice))
                    .monospacedDigit()
            }
            LabeledContent(language.text("label.target_price")) {
                Text(Self.currencyText(percentTargetPrice))
                    .monospacedDigit()
            }
        } else {
            Text(language.text("alert.percent_missing_baseline"))
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private func handleMetricChange(from oldMetric: AlertMetric, to newMetric: AlertMetric) {
        guard oldMetric != newMetric else { return }
        switch newMetric {
        case .price:
            threshold = currentPrice ?? alert?.lastPrice ?? alert?.baselinePrice ?? 0
            allowsNegativePercent = false
        case .percent:
            threshold = 0
            allowsNegativePercent = false
        }
        syncThresholdText(focused: isThresholdFocused)
    }

    private func startSave() {
        guard canSave else { return }
        Task { await save() }
    }

    private func attemptDismiss() {
        isThresholdFocused = false
        if hasUnsavedChanges {
            showDiscardConfirmation = true
        } else {
            dismiss()
        }
    }

    private func syncThresholdText(focused: Bool) {
        guard !isFormattingThreshold else { return }
        isFormattingThreshold = true
        thresholdText = Self.thresholdText(
            normalizedThreshold,
            metric: metric,
            focused: focused
        )
        isFormattingThreshold = false
    }

    private func normalizeThresholdText(_ text: String) {
        guard !isFormattingThreshold else { return }
        isFormattingThreshold = true
        switch metric {
        case .price:
            threshold = Self.currencyValue(from: text)
            thresholdText = Self.currencyText(threshold)
        case .percent:
            let normalizedText = Self.percentInputText(from: text)
            let parsedValue = Self.decimalValue(from: normalizedText)
            threshold = allowsNegativePercent ? -abs(parsedValue) : abs(parsedValue)
            thresholdText = normalizedText
        }
        isFormattingThreshold = false
    }

    private func resetPriceToBaseline() {
        guard let priceResetValue else { return }
        threshold = priceResetValue
        syncThresholdText(focused: isThresholdFocused)
    }

    private func save() async {
        isSaving = true
        let threshold = normalizedThreshold
        let baseline = metric == .percent ? percentBaselinePrice : nil
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

    private static func thresholdText(
        _ value: Double,
        metric: AlertMetric,
        focused: Bool
    ) -> String {
        switch metric {
        case .price:
            return currencyText(value)
        case .percent:
            return decimalText(abs(value), focused: focused)
        }
    }

    private static func currencyText(_ value: Double) -> String {
        "R$ \(decimalText(value, focused: false))"
    }

    private static func decimalText(_ value: Double, focused: Bool) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "pt_BR")
        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = focused ? 0 : 2
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: value)) ?? String(format: "%.2f", value).replacingOccurrences(of: ".", with: ",")
    }

    private static func currencyValue(from text: String) -> Double {
        let digits = text.compactMap(\.wholeNumberValue).map(String.init).joined()
        guard let cents = Double(digits), !digits.isEmpty else { return 0 }
        return cents / 100
    }

    private static func percentInputText(from text: String) -> String {
        var normalized = ""
        var hasDecimalSeparator = false
        for character in text {
            if let digit = character.wholeNumberValue {
                normalized.append(String(digit))
            } else if character == "." || character == ",", !hasDecimalSeparator {
                if normalized.isEmpty {
                    normalized = "0"
                }
                normalized.append(",")
                hasDecimalSeparator = true
            }
        }
        return normalized
    }

    private static func decimalValue(from text: String) -> Double {
        var normalized = ""
        var hasDecimalSeparator = false
        for character in text {
            if let digit = character.wholeNumberValue {
                normalized.append(String(digit))
            } else if character == "." || character == ",", !hasDecimalSeparator {
                if normalized.isEmpty {
                    normalized = "0"
                }
                normalized.append(".")
                hasDecimalSeparator = true
            }
        }
        return Double(normalized) ?? 0
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

private struct AlertEditorSnapshot: Equatable {
    let enabled: Bool
    let metric: AlertMetric
    let alertOperator: AlertOperator
    let threshold: Double
    let weekdays: [Int]
    let startTime: String
    let endTime: String
    let frequency: Int
    let cooldown: Int
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
