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
            code = Self.deviceLanguageCode()
        }
    }

    func text(_ key: String) -> String {
        Self.localized[key]?[code] ?? Self.localized[key]?[.en] ?? key
    }

    private static func deviceLanguageCode() -> AppLanguageCode {
        let preferredLanguage = Locale.preferredLanguages.first ?? Locale.current.identifier
        let languageCode = Locale(identifier: preferredLanguage).language.languageCode?.identifier
            ?? preferredLanguage
                .split(separator: "-")
                .first
                .map(String.init)
            ?? ""

        return languageCode.lowercased() == "pt" ? .pt : .en
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
        "app.title": [.pt: "Trade Alert", .en: "Trade Alert"],
        "tab.tracked": [.pt: "Acompanhadas", .en: "Tracked"],
        "tab.search": [.pt: "Buscar", .en: "Search"],
        "tab.notifications": [.pt: "Notificações", .en: "Notifications"],
        "tab.settings": [.pt: "Ajustes", .en: "Settings"],
        "section.delivery": [.pt: "Entrega", .en: "Delivery"],
        "section.devices": [.pt: "Dispositivos", .en: "Devices"],
        "section.plans": [.pt: "Planos", .en: "Plans"],
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
        "status.active": [.pt: "Ativo", .en: "Active"],
        "status.available": [.pt: "Disponível", .en: "Available"],
        "status.none": [.pt: "Nenhum plano ativo", .en: "No active plan"],
        "status.legacy": [.pt: "Você tem acesso legado da compra anterior.", .en: "You have legacy access from the previous purchase."],
        "status.active_summary": [.pt: "Ativo: %@", .en: "Active: %@"],
        "status.trial_days_left": [.pt: "Teste grátis: %d dias restantes", .en: "Free trial: %d days left"],
        "status.trial_day_left": [.pt: "Teste grátis: 1 dia restante", .en: "Free trial: 1 day left"],
        "action.allow_notifications": [.pt: "Permitir notificações", .en: "Allow Notifications"],
        "action.cancel": [.pt: "Cancelar", .en: "Cancel"],
        "action.not_now": [.pt: "Agora não", .en: "Not Now"],
        "action.ok": [.pt: "OK", .en: "OK"],
        "action.done": [.pt: "Concluído", .en: "Done"],
        "action.refresh": [.pt: "Atualizar", .en: "Refresh"],
        "action.track": [.pt: "Acompanhar", .en: "Track"],
        "action.untrack": [.pt: "Remover", .en: "Untrack"],
        "action.delete": [.pt: "Excluir", .en: "Delete"],
        "action.new_alert": [.pt: "Novo alerta", .en: "New Alert"],
        "action.save": [.pt: "Salvar", .en: "Save"],
        "action.update": [.pt: "Atualizar", .en: "Update"],
        "action.plans": [.pt: "Planos", .en: "Plans"],
        "action.close": [.pt: "Fechar", .en: "Close"],
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
        "paywall.title": [.pt: "Comece seu teste grátis", .en: "Start your free trial"],
        "paywall.subtitle": [
            .pt: "Para usar o Trade Alert, escolha um plano Pro, adquira a versão Vitalícia ou escolha o teste gratuito de 7 dias. O plano anual tem o melhor custo benefício.",
            .en: "To use Trade Alert, choose the Pro access plan, the Lifetime version or choose the 7-day free trial. The yearly plan has the best value."
        ],
        "paywall.loading": [.pt: "Carregando ofertas...", .en: "Loading offers..."],
        "paywall.checking_access": [.pt: "Verificando seu acesso...", .en: "Checking your access..."],
        "paywall.continue": [.pt: "Continuar", .en: "Continue"],
        "paywall.start_trial": [.pt: "Começar teste grátis", .en: "Start Free Trial"],
        "paywall.subscribe": [.pt: "Assinar agora", .en: "Subscribe Now"],
        "paywall.buy_lifetime": [.pt: "Comprar acesso vitalício", .en: "Buy Lifetime Access"],
        "paywall.restore": [.pt: "Restaurar compras", .en: "Restore Purchases"],
        "paywall.terms_privacy": [.pt: "Termos de Uso/Privacidade", .en: "Terms of Use/Privacy"],
        "paywall.enroll.title": [.pt: "Pro Anual", .en: "Pro Yearly"],
        "paywall.enroll.cta_trial": [.pt: "Começar 7 dias grátis", .en: "Start 7 Days Free"],
        "paywall.enroll.cta_subscribe": [.pt: "Assinar Pro Anual", .en: "Subscribe to Pro Yearly"],
        "paywall.other_plans.show": [.pt: "Ver outros planos", .en: "View Other Plans"],
        "paywall.other_plans.hide": [.pt: "Ocultar outros planos", .en: "Hide Other Plans"],
        "paywall.other_plans.title": [.pt: "Outros planos", .en: "Other Plans"],
        "paywall.trial.title": [.pt: "Teste gratuito de 7 dias", .en: "7-Day Free Trial"],
        "paywall.trial.ended.title": [.pt: "Solicitar novo teste de 7 dias", .en: "Request Another 7-Day Trial"],
        "paywall.trial.active.paywall_title": [.pt: "Seu teste grátis está ativo", .en: "Your free trial is active"],
        "paywall.trial.pending.paywall_title": [.pt: "Solicitação de teste em andamento", .en: "Trial request in progress"],
        "paywall.trial.ended.paywall_title": [.pt: "Seu teste terminou", .en: "Your trial has ended"],
        "paywall.trial.subtitle": [.pt: "Acesso completo por 7 dias, ativado pelo servidor.", .en: "Full access for 7 days."],
        "paywall.trial.cta": [.pt: "Solicitar teste de 7 dias", .en: "Request 7-Day Trial"],
        "paywall.trial.one_day.title": [.pt: "Seu teste termina amanhã", .en: "Your trial ends tomorrow"],
        "paywall.trial.one_day.message": [
            .pt: "Você tem 1 dia grátis restante. Escolha um plano para manter o acesso.",
            .en: "You have 1 free day left. Choose a plan to keep access."
        ],
        "paywall.trial.one_day.cta": [.pt: "Ver planos", .en: "View Plans"],
        "paywall.trial.wait.title": [.pt: "Teste solicitado", .en: "Trial requested"],
        "paywall.trial.wait.message": [.pt: "Seu pedido foi recebido. Aguarde a ativação do novo teste de 7 dias e volte mais tarde.", .en: "Your request was received. Please wait for the new 7-day trial to be activated and get back later."],
        "paywall.pro_year_unavailable.title": [
            .pt: "Plano anual indisponível",
            .en: "Yearly plan unavailable"
        ],
        "paywall.pro_year_unavailable.message": [
            .pt: "Não foi possível carregar o Pro Anual da App Store. Verifique se o produto pro_year está disponível no StoreKit/App Store Connect.",
            .en: "Could not load Pro Yearly from the App Store. Check that the pro_year product is available in StoreKit/App Store Connect."
        ],
        "paywall.loaded_products": [
            .pt: "Produtos carregados: %@",
            .en: "Loaded products: %@"
        ],
        "paywall.promo.pay_up_front": [
            .pt: "Oferta promocional: %@ por %@",
            .en: "Promotional offer: %@ for %@"
        ],
        "paywall.promo.pay_as_you_go": [
            .pt: "Oferta promocional: %@ por %@",
            .en: "Promotional offer: %@ for %@"
        ],
        "paywall.promo.free_trial": [
            .pt: "Oferta promocional: grátis por %@",
            .en: "Promotional offer: free for %@"
        ],
        "paywall.promo.generic": [
            .pt: "Oferta promocional: %@",
            .en: "Promotional offer: %@"
        ],
        "paywall.promo.regular_price": [
            .pt: "Depois, %@ por ano.",
            .en: "Then %@ per year."
        ],
        "paywall.period.day": [.pt: "%d dia", .en: "%d day"],
        "paywall.period.days": [.pt: "%d dias", .en: "%d days"],
        "paywall.period.week": [.pt: "%d semana", .en: "%d week"],
        "paywall.period.weeks": [.pt: "%d semanas", .en: "%d weeks"],
        "paywall.period.month": [.pt: "%d mês", .en: "%d month"],
        "paywall.period.months": [.pt: "%d meses", .en: "%d months"],
        "paywall.period.year": [.pt: "%d ano", .en: "%d year"],
        "paywall.period.years": [.pt: "%d anos", .en: "%d years"],
        "paywall.feature.alerts.title": [.pt: "Alertas da B3", .en: "B3 alerts"],
        "paywall.feature.alerts.subtitle": [
            .pt: "Acompanhe tickers, favoritos e regras por preço ou percentual.",
            .en: "Track tickers, favorites, and price or percentage rules."
        ],
        "paywall.feature.watch.title": [.pt: "iPhone, iPad e Apple Watch", .en: "iPhone, iPad, and Apple Watch"],
        "paywall.feature.watch.subtitle": [
            .pt: "Receba notificações nos dispositivos configurados.",
            .en: "Receive notifications on your configured devices."
        ],
        "paywall.feature.restore.title": [.pt: "Acesso restaurável", .en: "Restorable access"],
        "paywall.feature.restore.subtitle": [
            .pt: "Assinaturas e compras vitalícias podem ser restauradas pela App Store.",
            .en: "Subscriptions and lifetime purchases can be restored through the App Store."
        ],
        "paywall.product.pro_year.title": [.pt: "Pro Anual", .en: "Pro Yearly"],
        "paywall.product.pro_year.trial_subtitle": [
            .pt: "7 dias grátis, depois %@ por ano.",
            .en: "7 days free, then %@ per year."
        ],
        "paywall.product.pro_year.subtitle": [
            .pt: "Acesso Pro por %@ ao ano.",
            .en: "Pro access for %@ per year."
        ],
        "paywall.product.pro_month.title": [.pt: "Pro Mensal", .en: "Pro Monthly"],
        "paywall.product.pro_month.subtitle": [
            .pt: "Acesso Pro por %@ ao mês.",
            .en: "Pro access for %@ per month."
        ],
        "paywall.product.lifetime.title": [.pt: "Acesso Vitalício", .en: "Lifetime Unlock"],
        "paywall.product.lifetime.subtitle": [
            .pt: "Pagamento único para manter o acesso completo.",
            .en: "One-time payment to keep full access."
        ],
        "paywall.badge.trial": [.pt: "7 dias grátis", .en: "7 days free"],
        "paywall.badge.best_value": [.pt: "Melhor valor", .en: "Best value"],
        "paywall.badge.once": [.pt: "Pagamento único", .en: "One-time"],
        "paywall.price.year": [.pt: "por ano", .en: "per year"],
        "paywall.price.month": [.pt: "por mês", .en: "per month"],
        "paywall.price.once": [.pt: "uma vez", .en: "once"],
        "purchase.pending": [
            .pt: "A compra está pendente de aprovação.",
            .en: "The purchase is pending approval."
        ],
        "purchase.restore.none": [
            .pt: "Nenhuma compra ativa foi encontrada para restaurar.",
            .en: "No active purchases were found to restore."
        ],
        "purchase.error.load_products": [
            .pt: "Não foi possível carregar as ofertas: %@",
            .en: "Could not load offers: %@"
        ],
        "purchase.error.purchase_failed": [
            .pt: "Não foi possível concluir a compra: %@",
            .en: "Could not complete the purchase: %@"
        ],
        "purchase.error.restore_failed": [
            .pt: "Não foi possível restaurar as compras: %@",
            .en: "Could not restore purchases: %@"
        ],
        "purchase.error.verification": [
            .pt: "A compra não pôde ser verificada.",
            .en: "The purchase could not be verified."
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
