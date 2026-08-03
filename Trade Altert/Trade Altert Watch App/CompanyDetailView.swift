import Foundation
import SwiftUI

struct CompanyDetailView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var language: AppLanguage
    @State private var company: Company

    init(company: Company) {
        _company = State(initialValue: company)
    }

    private var isFavorite: Bool {
        model.favorites.contains { $0.ticker == company.ticker }
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(company.ticker)
                        .font(.title3.bold())
                    Text(company.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let price = company.lastPrice {
                        Text(price, format: .currency(code: "BRL"))
                            .font(.headline)
                    }
                    if let change = company.dailyChangePercent {
                        Text(change / 100, format: .percent.precision(.fractionLength(2)))
                            .foregroundStyle(change >= 0 ? .green : .red)
                    }
                }

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
        .task {
            await reload()
            await model.loadAlerts(ticker: company.ticker)
        }
        .refreshable {
            await reload()
            await model.loadAlerts(ticker: company.ticker)
        }
    }

    private func reload() async {
        do {
            company = try await APIClient.shared.quote(ticker: company.ticker)
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }
}

struct AlertRow: View {
    @EnvironmentObject private var language: AppLanguage

    let alert: AlertRule

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(alert.metric == .price
                    ? "\(language.text("alert.price_prefix")) \(alert.operator.label)"
                    : "\(language.text("alert.move_prefix")) \(alert.operator.label)")
                if !alert.enabled {
                    Text(language.text("alert.paused"))
                }
            }
            .font(.caption)
            Text(alert.metric == .price ? currency(alert.threshold) : percent(alert.threshold))
                .font(.headline)
            Text(language.alertWindow(start: alert.startTime, end: alert.endTime, frequency: alert.frequencyMinutes))
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "BRL"))
    }

    private func percent(_ value: Double) -> String {
        String(format: "%.2f%%", value)
    }
}
