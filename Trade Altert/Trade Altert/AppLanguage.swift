import Foundation
import Combine

enum AppLanguageCode: String, CaseIterable, Identifiable {
    case pt
    case en

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .pt: return "Português"
        case .en: return "English"
        }
    }

    var locale: Locale {
        switch self {
        case .pt: return Locale(identifier: "pt_BR")
        case .en: return Locale(identifier: "en_US")
        }
    }
}

final class AppLanguage: ObservableObject {
    static let shared = AppLanguage()

    @Published var code: AppLanguageCode {
        didSet {
            UserDefaults.standard.set(code.rawValue, forKey: Self.storageKey)
        }
    }

    var locale: Locale {
        code.locale
    }

    private static let storageKey = "tradealert.language"

    private init() {
        if let stored = UserDefaults.standard.string(forKey: Self.storageKey),
           let storedCode = AppLanguageCode(rawValue: stored) {
            code = storedCode
        } else {
            code = .pt
        }
    }

    func text(_ key: String) -> String {
        Self.localized[key]?[code] ?? Self.localized[key]?[.pt] ?? key
    }

    func everyMinutes(_ minutes: Int) -> String {
        String(format: text("schedule.every_minutes"), minutes)
    }

    func cooldownMinutes(_ minutes: Int) -> String {
        String(format: text("schedule.cooldown_minutes"), minutes)
    }

    func alertWindow(start: String, end: String, frequency: Int) -> String {
        String(format: text("alert.window_summary"), start, end, frequency)
    }

    private static let localized: [String: [AppLanguageCode: String]] = [
        "app.title": [.pt: "B3 Watch", .en: "B3 Watch"],
        "tab.tracked": [.pt: "Acompanhadas", .en: "Tracked"],
        "tab.search": [.pt: "Buscar", .en: "Search"],
        "tab.notifications": [.pt: "Notificações", .en: "Notifications"],
        "tab.settings": [.pt: "Ajustes", .en: "Settings"],
        "section.delivery": [.pt: "Entrega", .en: "Delivery"],
        "section.devices": [.pt: "Dispositivos", .en: "Devices"],
        "section.server": [.pt: "Servidor", .en: "Server"],
        "section.language": [.pt: "Idioma", .en: "Language"],
        "section.alerts": [.pt: "Alertas", .en: "Alerts"],
        "section.week": [.pt: "Semana", .en: "Week"],
        "section.window": [.pt: "Janela", .en: "Window"],
        "label.iphone": [.pt: "iPhone", .en: "iPhone"],
        "label.apple_watch": [.pt: "Apple Watch", .en: "Apple Watch"],
        "label.mode": [.pt: "Modo", .en: "Mode"],
        "label.api": [.pt: "API", .en: "API"],
        "label.enabled": [.pt: "Ativo", .en: "Enabled"],
        "label.metric": [.pt: "Métrica", .en: "Metric"],
        "label.target": [.pt: "Alvo", .en: "Target"],
        "label.start": [.pt: "Início", .en: "Start"],
        "label.end": [.pt: "Fim", .en: "End"],
        "label.ticker": [.pt: "Ticker", .en: "Ticker"],
        "label.brl": [.pt: "BRL", .en: "BRL"],
        "label.percent": [.pt: "Percentual", .en: "Percent"],
        "label.debug": [.pt: "Debug", .en: "Debug"],
        "label.production": [.pt: "Produção", .en: "Production"],
        "status.registered": [.pt: "Registrado", .en: "Registered"],
        "status.not_registered": [.pt: "Não registrado", .en: "Not registered"],
        "action.allow_notifications": [.pt: "Permitir notificações", .en: "Allow Notifications"],
        "action.not_now": [.pt: "Agora não", .en: "Not Now"],
        "action.ok": [.pt: "OK", .en: "OK"],
        "action.track": [.pt: "Acompanhar", .en: "Track"],
        "action.untrack": [.pt: "Remover", .en: "Untrack"],
        "action.delete": [.pt: "Excluir", .en: "Delete"],
        "action.new_alert": [.pt: "Novo alerta", .en: "New Alert"],
        "action.save": [.pt: "Salvar", .en: "Save"],
        "action.update": [.pt: "Atualizar", .en: "Update"],
        "title.edit_alert": [.pt: "Editar alerta", .en: "Edit Alert"],
        "title.search": [.pt: "Buscar", .en: "Search"],
        "title.tracked": [.pt: "Acompanhadas", .en: "Tracked"],
        "title.notifications": [.pt: "Notificações", .en: "Notifications"],
        "title.error": [.pt: "Erro", .en: "Error"],
        "title.almost_ready": [.pt: "Quase pronto", .en: "Almost ready"],
        "message.notification_permission": [
            .pt: "Precisamos da sua permissão para enviar notificações.",
            .en: "We need your permission to send notifications."
        ],
        "message.notifications_disabled": [
            .pt: "As notificações estão desativadas neste iPhone.",
            .en: "Notifications are disabled for this iPhone."
        ],
        "empty.search": [.pt: "Busque tickers B3", .en: "Search B3 Tickers"],
        "empty.no_results": [.pt: "Nenhum resultado", .en: "No Results"],
        "empty.no_tracked": [.pt: "Nenhuma empresa acompanhada", .en: "No Tracked Companies"],
        "empty.no_tickers": [.pt: "Nenhum ticker", .en: "No tickers"],
        "prompt.search": [.pt: "Ticker ou empresa", .en: "Ticker or company"],
        "metric.price": [.pt: "Preço", .en: "Price"],
        "metric.percent": [.pt: "Percentual", .en: "Percent"],
        "operator.gte": [.pt: "Acima", .en: "Above"],
        "operator.lte": [.pt: "Abaixo", .en: "Below"],
        "alert.price_prefix": [.pt: "Preço", .en: "Price"],
        "alert.move_prefix": [.pt: "Variação", .en: "Move"],
        "alert.paused": [.pt: "Pausado", .en: "Paused"],
        "alert.window_summary": [.pt: "%@-%@ a cada %dm", .en: "%@-%@ every %dm"],
        "schedule.every_minutes": [.pt: "A cada %dm", .en: "Every %dm"],
        "schedule.cooldown_minutes": [.pt: "Intervalo %dm", .en: "Cooldown %dm"],
        "weekday.1": [.pt: "Seg", .en: "Mon"],
        "weekday.2": [.pt: "Ter", .en: "Tue"],
        "weekday.3": [.pt: "Qua", .en: "Wed"],
        "weekday.4": [.pt: "Qui", .en: "Thu"],
        "weekday.5": [.pt: "Sex", .en: "Fri"],
        "weekday.6": [.pt: "Sáb", .en: "Sat"],
        "weekday.7": [.pt: "Dom", .en: "Sun"],
        "api.invalid_url": [.pt: "URL da API inválida", .en: "Invalid API URL"],
    ]
}
