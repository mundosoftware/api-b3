import Charts
import SwiftUI
import UIKit

struct CompanyDetailView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @State private var company: Company
    @State private var aiAnalysis: DecisionSupportAnalysis?
    @State private var aiHorizon = 10
    @State private var aiIsLoading = false
    @State private var aiError: String?
    @State private var aiRequestID = UUID()
    @State private var aiToggleIsLoading = false
    @State private var aiCopyToastMessage: String?
    @State private var aiCopyToastID = UUID()
    @State private var showAIActivationDisclosure = false

    init(company: Company) {
        _company = State(initialValue: company)
    }

    private var isFavorite: Bool {
        model.favorites.contains { $0.ticker == company.ticker }
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Text(company.ticker)
                        .font(.title2.bold())
                    Text(company.name)
                        .foregroundStyle(.secondary)
                    if let price = company.lastPrice {
                        Text(price, format: .currency(code: "BRL"))
                            .font(.title3)
                            .monospacedDigit()
                    }
                    if let change = company.dailyChangePercent {
                        Text(change / 100, format: .percent.precision(.fractionLength(2)))
                            .foregroundStyle(change >= 0 ? .green : .red)
                            .monospacedDigit()
                    }
                }
                .padding(.vertical, 4)

                Button {
                    Task {
                        if isFavorite {
                            await model.removeFavorite(company.ticker)
                        } else {
                            await model.addFavorite(company.ticker)
                        }
                    }
                } label: {
                    Label(
                        isFavorite ? language.text("action.untrack") : language.text("action.track"),
                        systemImage: isFavorite ? "star.fill" : "star"
                    )
                }
            }

            aiSection

            Section(language.text("section.alerts")) {
                NavigationLink {
                    AlertEditorView(ticker: company.ticker, currentPrice: company.lastPrice)
                } label: {
                    Label(language.text("action.new_alert"), systemImage: "bell.badge")
                }

                ForEach(model.alertsByTicker[company.ticker] ?? []) { alert in
                    NavigationLink {
                        AlertEditorView(ticker: company.ticker, currentPrice: company.lastPrice, alert: alert)
                    } label: {
                        AlertRow(alert: alert)
                    }
                        .swipeActions {
                            Button(role: .destructive) {
                                Task { await model.deleteAlert(alert) }
                            } label: {
                                Label(language.text("action.delete"), systemImage: "trash")
                            }
                        }
                }
            }
        }
        .navigationTitle(company.ticker)
        .overlay(alignment: .top) {
            if let aiCopyToastMessage {
                AITextCopyToast(message: aiCopyToastMessage)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .zIndex(1)
            }
        }
        .task {
            await reload()
            await model.refreshAIOutlookFeatureStatus(force: false)
            if model.aiOutlookAvailable && model.aiOutlookEnabled {
                await loadAIAnalysis()
            }
            await model.loadAlerts(ticker: company.ticker)
        }
        .refreshable {
            await reload()
            await model.refreshAIOutlookFeatureStatus()
            await model.loadAlerts(ticker: company.ticker)
        }
        .onChange(of: aiHorizon) { _, _ in
            guard model.aiOutlookAvailable, model.aiOutlookEnabled else { return }
            Task {
                await loadAIAnalysis(forceRefresh: true)
            }
        }
        .onChange(of: model.aiOutlookEnabled) { _, enabled in
            guard model.aiOutlookAvailable, enabled, aiAnalysis == nil, !aiToggleIsLoading else { return }
            Task {
                await loadAIAnalysis()
            }
        }
        .onChange(of: model.aiOutlookAvailable) { _, available in
            if !available {
                resetAIOutlookData()
            } else if model.aiOutlookEnabled && aiAnalysis == nil {
                Task {
                    await loadAIAnalysis()
                }
            }
        }
        .alert(language.text("ai.ftue.title"), isPresented: $showAIActivationDisclosure) {
            Button(language.text("action.ok"), role: .cancel) {}
        } message: {
            Text(language.text("ai.ftue.message"))
        }
    }

    private var aiSection: some View {
        Section(language.text("section.ai_outlook")) {
            if !model.aiOutlookAvailable {
                AIOutlookMaintenanceView()
            } else if !model.aiOutlookEnabled {
                AIEnableOutlookView(isLoading: aiToggleIsLoading) {
                    Task {
                        await toggleAIOutlook()
                    }
                }
            } else {
                Picker(language.text("label.horizon"), selection: $aiHorizon) {
                    Text("5").tag(5)
                    Text("10").tag(10)
                    Text("20").tag(20)
                }
                .pickerStyle(.segmented)
                .disabled(aiIsLoading)

                if aiIsLoading {
                    HStack {
                        ProgressView()
                        Text(aiAnalysis == nil ? language.text("ai.loading") : language.text("ai.updating"))
                            .foregroundStyle(.secondary)
                    }
                }

                if let aiAnalysis {
                    AIOutlookView(
                        analysis: aiAnalysis,
                        isLoading: aiIsLoading,
                        onCopyForTranslation: copyAITextForTranslation
                    )
                }

                if let aiError {
                    Text(aiError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }

                Button {
                    Task {
                        await loadAIAnalysis(forceRefresh: true)
                    }
                } label: {
                    Label(language.text("ai.refresh"), systemImage: "arrow.clockwise")
                }
                .disabled(aiIsLoading)

                AIOutlookActivationCTA(
                    isEnabled: true,
                    isLoading: aiToggleIsLoading,
                    role: .destructive
                ) {
                    Task {
                        await toggleAIOutlook()
                    }
                }
            }
        }
    }

    private func reload() async {
        do {
            company = try await CompanionAPIClient.shared.quote(ticker: company.ticker)
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }

    private func loadAIAnalysis(forceRefresh: Bool = false) async {
        guard model.aiOutlookAvailable, model.aiOutlookEnabled else { return }
        let interval = "1d"
        let requestID = UUID()
        let requestHorizon = aiHorizon
        if !forceRefresh {
            if let current = aiAnalysis,
               current.ticker.uppercased() == company.ticker.uppercased(),
               current.interval == interval,
               current.horizon == requestHorizon {
                return
            }
            if let cached = model.cachedAIAnalysis(
                ticker: company.ticker,
                interval: interval,
                horizon: requestHorizon
            ) {
                aiAnalysis = cached
                aiError = nil
                return
            }
        }
        aiRequestID = requestID
        aiIsLoading = true
        aiError = nil
        do {
            let analysis = try await CompanionAPIClient.shared.aiAnalysis(
                ticker: company.ticker,
                interval: interval,
                horizon: requestHorizon,
                forceRefresh: forceRefresh
            )
            if aiRequestID == requestID && model.aiOutlookAvailable && model.aiOutlookEnabled {
                aiAnalysis = analysis
                model.storeAIAnalysis(analysis)
            }
        } catch {
            if aiRequestID == requestID {
                aiError = language.aiOutlookErrorText(error)
            }
        }
        if aiRequestID == requestID {
            aiIsLoading = false
        }
    }

    private func toggleAIOutlook() async {
        guard model.aiOutlookAvailable else { return }
        let shouldEnable = !model.aiOutlookEnabled
        aiToggleIsLoading = true
        let updated = await model.updateAIOutlookEnabled(shouldEnable)
        aiToggleIsLoading = false
        guard updated else { return }

        if !shouldEnable {
            resetAIOutlookData()
            return
        }

        showAIActivationDisclosure = true
        await loadAIAnalysis()
    }

    private func resetAIOutlookData() {
        aiRequestID = UUID()
        aiIsLoading = false
        aiError = nil
        aiAnalysis = nil
    }

    private func copyAITextForTranslation(_ text: String) {
        UIPasteboard.general.string = text
        let toastID = UUID()
        aiCopyToastID = toastID
        withAnimation(.easeInOut(duration: 0.2)) {
            aiCopyToastMessage = language.text("ai.copy_translate_toast")
        }
        Task {
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            await MainActor.run {
                guard aiCopyToastID == toastID else { return }
                withAnimation(.easeInOut(duration: 0.2)) {
                    aiCopyToastMessage = nil
                }
            }
        }
    }
}

struct AIOutlookMaintenanceView: View {
    @EnvironmentObject private var language: AppLanguage

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(language.text("ai.maintenance.title"), systemImage: "wrench.and.screwdriver")
                .font(.headline)
            Text(language.text("ai.maintenance.message"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
    }
}

struct AIEnableOutlookView: View {
    @EnvironmentObject private var language: AppLanguage

    let isLoading: Bool
    let onEnable: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("ai.enable.title"))
                .font(.headline)
            VStack(alignment: .leading, spacing: 8) {
                benefit(language.text("ai.enable.benefit.forecast"), systemImage: "chart.xyaxis.line")
                benefit(language.text("ai.enable.benefit.research"), systemImage: "doc.text.magnifyingglass")
                benefit(language.text("ai.enable.benefit.model"), systemImage: "server.rack")
                benefit(language.text("ai.enable.benefit.levels"), systemImage: "line.3.horizontal.decrease")
                benefit(language.text("ai.enable.benefit.risk"), systemImage: "exclamationmark.shield")
            }

            AIOutlookSourceLinks()

            AIOutlookActivationCTA(isEnabled: false, isLoading: isLoading, action: onEnable)
        }
        .padding(.vertical, 6)
    }

    private func benefit(_ text: String, systemImage: String) -> some View {
        Label(text, systemImage: systemImage)
            .font(.subheadline)
            .foregroundStyle(.secondary)
    }
}

struct AIOutlookSourceLinks: View {
    @EnvironmentObject private var language: AppLanguage

    private let paperURL = URL(string: "https://arxiv.org/abs/2508.02739")!
    private let sourceURL = URL(string: "https://github.com/shiyu-coder/Kronos")!

    var body: some View {
        HStack(spacing: 16) {
            Link(language.text("ai.source.paper"), destination: paperURL)
            Link(language.text("ai.source.code"), destination: sourceURL)
        }
        .font(.footnote.weight(.semibold))
    }
}

struct AIOutlookActivationCTA: View {
    @EnvironmentObject private var language: AppLanguage

    let isEnabled: Bool
    let isLoading: Bool
    var role: ButtonRole?
    let action: () -> Void

    var body: some View {
        Button(role: role, action: action) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
        }
        .buttonStyle(.borderedProminent)
        .disabled(isLoading)
    }

    private var title: String {
        if isLoading {
            return language.text(isEnabled ? "ai.disable.loading_cta" : "ai.enable.loading_cta")
        }
        return language.text(isEnabled ? "ai.disable.cta" : "ai.enable.cta")
    }
}

struct AIOutlookView: View {
    @EnvironmentObject private var language: AppLanguage

    let analysis: DecisionSupportAnalysis
    let isLoading: Bool
    let onCopyForTranslation: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                Label(outlookLabel, systemImage: outlookIcon)
                    .font(.headline)
                    .foregroundStyle(outlookColor)
                Spacer()
                Text(analysis.expectedChangePercent / 100, format: .percent.precision(.fractionLength(2)))
                    .font(.title3.bold())
                    .monospacedDigit()
                    .foregroundStyle(outlookColor)
            }

            Text(analysis.summary)
                .font(.subheadline)
            Text(analysis.action)
                .font(.footnote)
                .foregroundStyle(.secondary)
            if showsCopyControls {
                AITextCopyCTA(isLoading: isLoading) {
                    onCopyForTranslation(summaryActionText)
                }
            }

            DecisionForecastChart(analysis: analysis)

            Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
                GridRow {
                    metric(language.text("ai.target"), currency(analysis.targetPrice))
                    metric(language.text("ai.confidence"), unsignedPercent(analysis.confidence * 100))
                }
                GridRow {
                    metric(language.text("ai.support"), currency(analysis.supportPrice))
                    metric(language.text("ai.resistance"), currency(analysis.resistancePrice))
                }
                GridRow {
                    metric(language.text("ai.forecast_range"), forecastRange)
                    metric(language.text("ai.risk"), riskLabel)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(language.text("ai.drivers"))
                    .font(.caption.bold())
                ForEach(analysis.drivers.prefix(4), id: \.self) { driver in
                    Label(driver, systemImage: "checkmark.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if showsCopyControls {
                    AITextCopyCTA(isLoading: isLoading) {
                        onCopyForTranslation(driversText)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(language.text("ai.warnings"))
                    .font(.caption.bold())
                ForEach(analysis.warnings.prefix(3), id: \.self) { warning in
                    Label(language.aiWarningText(warning), systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Text("\(analysis.modelName) · \(analysis.source.uppercased()) · \(analysis.generatedAt)")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .lineLimit(2)
        }
        .padding(.vertical, 6)
        .opacity(isLoading ? 0.55 : 1)
        .overlay {
            if isLoading {
                ProgressView(language.text("ai.updating"))
                    .padding(12)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private var showsCopyControls: Bool {
        language.code == .pt
    }

    private var summaryActionText: String {
        "\(analysis.summary)\n\n\(analysis.action)"
    }

    private var driversText: String {
        analysis.drivers.prefix(4).joined(separator: "\n")
    }

    private var outlookLabel: String {
        language.text("ai.outlook.\(analysis.outlook)")
    }

    private var riskLabel: String {
        language.text("ai.risk.\(analysis.riskLevel)")
    }

    private var outlookIcon: String {
        switch analysis.outlook {
        case "bullish": return "chart.line.uptrend.xyaxis"
        case "bearish": return "chart.line.downtrend.xyaxis"
        default: return "waveform.path.ecg"
        }
    }

    private var outlookColor: Color {
        switch analysis.outlook {
        case "bullish": return .green
        case "bearish": return .red
        default: return .orange
        }
    }

    private var forecastRange: String {
        "\(percent(analysis.forecastLowPercent)) / \(percent(analysis.forecastHighPercent))"
    }

    private func metric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "BRL"))
    }

    private func percent(_ value: Double) -> String {
        String(format: "%+.2f%%", value)
    }

    private func unsignedPercent(_ value: Double) -> String {
        String(format: "%.0f%%", value)
    }
}

struct AITextCopyCTA: View {
    @EnvironmentObject private var language: AppLanguage

    let isLoading: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(language.text("ai.copy_text"))
                .font(.caption.weight(.semibold))
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 5)
        }
        .buttonStyle(.bordered)
        .disabled(isLoading)
    }
}

struct AITextCopyToast: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.caption.weight(.semibold))
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            .shadow(radius: 10, y: 4)
    }
}

struct DecisionForecastChart: View {
    let analysis: DecisionSupportAnalysis

    private var historicalPoints: [AIChartPoint] {
        analysis.historical.compactMap { candle -> AIChartPoint? in
            guard let date = Self.date(from: candle.timestamp) else { return nil }
            return AIChartPoint(id: "h-\(candle.timestamp)", date: date, close: candle.close)
        }
    }

    private var forecastPoints: [AIChartPoint] {
        var points: [AIChartPoint] = analysis.forecast.compactMap { candle -> AIChartPoint? in
            guard let date = Self.date(from: candle.timestamp) else { return nil }
            return AIChartPoint(id: "f-\(candle.timestamp)", date: date, close: candle.close)
        }
        if let last = historicalPoints.last {
            points.insert(AIChartPoint(id: "f-anchor-\(last.id)", date: last.date, close: last.close), at: 0)
        }
        return points
    }

    var body: some View {
        Chart {
            ForEach(historicalPoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Close", point.close)
                )
                .foregroundStyle(.blue)
                .lineStyle(StrokeStyle(lineWidth: 2))
            }

            ForEach(forecastPoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Forecast", point.close)
                )
                .foregroundStyle(.orange)
                .lineStyle(StrokeStyle(lineWidth: 2.5, dash: [5, 3]))
            }

            RuleMark(y: .value("Support", analysis.supportPrice))
                .foregroundStyle(.red.opacity(0.45))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))

            RuleMark(y: .value("Resistance", analysis.resistancePrice))
                .foregroundStyle(.green.opacity(0.45))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
        }
        .frame(height: 220)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4))
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
    }

    private static func date(from value: String) -> Date? {
        fractionalISODateFormatter.date(from: value) ?? isoDateFormatter.date(from: value)
    }

    private static let isoDateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let fractionalISODateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

struct AIChartPoint: Identifiable {
    let id: String
    let date: Date
    let close: Double
}

struct AlertRow: View {
    @EnvironmentObject private var language: AppLanguage

    let alert: AlertRule

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(alert.metric == .price
                    ? "\(language.text("alert.price_prefix")) \(alert.operator.label)"
                    : "\(language.text("alert.move_prefix")) \(alert.operator.label)")
                if !alert.enabled {
                    Text(language.text("alert.paused"))
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            Text(alert.metric == .price ? currency(alert.threshold) : percent(alert.threshold))
                .font(.headline)
            Text(language.alertWindow(start: alert.startTime, end: alert.endTime, frequency: alert.frequencyMinutes))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 3)
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "BRL"))
    }

    private func percent(_ value: Double) -> String {
        String(format: "%.2f%%", value)
    }
}
