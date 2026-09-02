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

    func aiWarningText(_ warning: String) -> String {
        switch warning {
        case "Forecasts are probabilistic and can be wrong.":
            return text("ai.warning.forecasts_probabilistic")
        case "This is decision support, not investment advice.":
            return text("ai.warning.not_investment_advice")
        case "Yahoo chart data may be delayed or incomplete.":
            return text("ai.warning.yahoo_data")
        default:
            return warning
        }
    }

    func aiOutlookErrorText(_ error: Error) -> String {
        if let apiError = error as? CompanionAPIError {
            switch apiError {
            case .invalidURL:
                return text("ai.error.generic")
            case let .badResponse(status, _):
                switch status {
                case 404:
                    return text("ai.error.not_found")
                case 408, 504:
                    return text("ai.error.timeout")
                case 429:
                    return text("ai.error.busy")
                case 500...599:
                    return text("ai.error.unavailable")
                default:
                    return text("ai.error.generic")
                }
            }
        }

        if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost, .cannotFindHost:
                return text("ai.error.network")
            case .timedOut:
                return text("ai.error.timeout")
            default:
                return text("ai.error.generic")
            }
        }

        return text("ai.error.generic")
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
        "section.ai_outlook": [.pt: "Perspectiva IA", .en: "AI Outlook"],
        "section.week": [.pt: "Semana", .en: "Week"],
        "section.window": [.pt: "Janela", .en: "Window"],
        "label.iphone": [.pt: "iPhone", .en: "iPhone"],
        "label.apple_watch": [.pt: "Apple Watch", .en: "Apple Watch"],
        "label.mode": [.pt: "Modo", .en: "Mode"],
        "label.api": [.pt: "API", .en: "API"],
        "label.enabled": [.pt: "Ativo", .en: "Enabled"],
        "label.metric": [.pt: "Métrica", .en: "Metric"],
        "label.target": [.pt: "Alvo", .en: "Target"],
        "label.horizon": [.pt: "Horizonte", .en: "Horizon"],
        "label.start": [.pt: "Início", .en: "Start"],
        "label.end": [.pt: "Fim", .en: "End"],
        "label.ticker": [.pt: "Ticker", .en: "Ticker"],
        "label.brl": [.pt: "BRL", .en: "BRL"],
        "label.percent": [.pt: "Percentual", .en: "Percent"],
        "label.negative_percent": [.pt: "Percentual negativo", .en: "Negative percent"],
        "label.based_on_price": [.pt: "Preço base", .en: "Base price"],
        "label.target_price": [.pt: "Preço-alvo", .en: "Target price"],
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
        "action.reset": [.pt: "Redefinir", .en: "Reset"],
        "action.track": [.pt: "Acompanhar", .en: "Track"],
        "action.untrack": [.pt: "Remover", .en: "Untrack"],
        "action.delete": [.pt: "Excluir", .en: "Delete"],
        "action.new_alert": [.pt: "Novo alerta", .en: "New Alert"],
        "action.save": [.pt: "Salvar", .en: "Save"],
        "action.update": [.pt: "Atualizar", .en: "Update"],
        "action.discard": [.pt: "Descartar", .en: "Discard"],
        "action.keep_editing": [.pt: "Continuar editando", .en: "Keep Editing"],
        "action.plans": [.pt: "Planos", .en: "Plans"],
        "action.close": [.pt: "Fechar", .en: "Close"],
        "ai.loading": [.pt: "Analisando candles...", .en: "Analyzing candles..."],
        "ai.updating": [.pt: "Atualizando análise...", .en: "Updating analysis..."],
        "ai.refresh": [.pt: "Atualizar análise IA", .en: "Refresh AI analysis"],
        "ai.retry_cta": [.pt: "Tentar novamente", .en: "Try again"],
        "ai.cancel.cta": [.pt: "Cancelar análise IA", .en: "Cancel AI analysis"],
        "ai.cancel.loading_cta": [.pt: "Cancelando análise...", .en: "Canceling analysis..."],
        "ai.cancel.confirm_title": [.pt: "Cancelar análise IA?", .en: "Cancel AI analysis?"],
        "ai.cancel.confirm_message": [
            .pt: "A solicitação em andamento será cancelada e removida deste dispositivo.",
            .en: "The in-progress request will be canceled and removed from this device."
        ],
        "ai.cancel.confirm_cta": [.pt: "Cancelar análise", .en: "Cancel analysis"],
        "ai.job.queued_title": [.pt: "Análise IA na fila", .en: "AI analysis queued"],
        "ai.job.queued_message": [
            .pt: "Este modelo é complexo e a análise pode demorar. Você pode sair desta tela; avisaremos quando estiver pronta.",
            .en: "This model is complex and the analysis can take a while. You can leave this screen; we will notify you when it is ready."
        ],
        "ai.job.running_title": [.pt: "Análise IA em andamento", .en: "AI analysis running"],
        "ai.job.running_message": [
            .pt: "Estamos processando os candles e limitando a IA a uma análise por vez para manter o servidor estável.",
            .en: "We are processing the candles and limiting AI to one analysis at a time to keep the server stable."
        ],
        "ai.job.retrying_title": [.pt: "Tentando novamente", .en: "Retrying analysis"],
        "ai.job.retrying_message": [
            .pt: "A tentativa %d de %d falhou. Vamos tentar novamente automaticamente.",
            .en: "Attempt %d of %d failed. We will retry automatically."
        ],
        "ai.job.failed_title": [.pt: "A análise não finalizou", .en: "Analysis did not finish"],
        "ai.job.failed_message": [
            .pt: "A análise falhou após %d tentativas. Tente novamente quando quiser.",
            .en: "The analysis failed after %d attempts. Try again whenever you are ready."
        ],
        "ai.job.canceled_title": [.pt: "Análise IA cancelada", .en: "AI analysis canceled"],
        "ai.job.canceled_message": [
            .pt: "A solicitação foi cancelada e removida deste dispositivo.",
            .en: "The request was canceled and removed from this device."
        ],
        "ai.job.succeeded_title": [.pt: "Análise pronta", .en: "Analysis ready"],
        "ai.job.succeeded_message": [
            .pt: "A Perspectiva IA terminou e foi atualizada abaixo.",
            .en: "AI Outlook finished and has been updated below."
        ],
        "ai.job.attempts": [.pt: "Tentativa %d de %d", .en: "Attempt %d of %d"],
        "ai.copy_text": [.pt: "Copiar texto", .en: "Copy text"],
        "ai.copy_translate_toast": [
            .pt: "Texto copiado. Cole no seu tradutor favorito para traduzir.",
            .en: "Text copied. Paste it into your favorite translator app."
        ],
        "ai.enable.title": [.pt: "Ative previsões com IA", .en: "Enable AI forecasts"],
        "ai.enable.benefit.forecast": [
            .pt: "Veja uma projeção visual dos próximos candles.",
            .en: "See a visual projection of the next candles."
        ],
        "ai.enable.benefit.research": [
            .pt: "Baseado no paper Kronos do arXiv, com aceite na AAAI 2026.",
            .en: "Based on the Kronos arXiv paper, accepted at AAAI 2026."
        ],
        "ai.enable.benefit.model": [
            .pt: "Usa um modelo aberto criado para sequências OHLCV de mercado.",
            .en: "Uses an open model built for market OHLCV sequences."
        ],
        "ai.enable.benefit.levels": [
            .pt: "Receba suporte, resistência e preço-alvo estimados.",
            .en: "Get estimated support, resistance, and target levels."
        ],
        "ai.enable.benefit.risk": [
            .pt: "Compare tendência, faixa prevista, confiança e risco.",
            .en: "Compare trend, forecast range, confidence, and risk."
        ],
        "ai.enable.cta": [.pt: "Ativar Perspectiva IA", .en: "Enable AI Outlook"],
        "ai.enable.loading_cta": [.pt: "Ativando Perspectiva IA...", .en: "Enabling AI Outlook..."],
        "ai.disable.cta": [.pt: "Desativar Perspectiva IA", .en: "Disable AI Outlook"],
        "ai.disable.loading_cta": [.pt: "Desativando Perspectiva IA...", .en: "Disabling AI Outlook..."],
        "ai.disable.confirm_title": [.pt: "Desativar Perspectiva IA?", .en: "Disable AI Outlook?"],
        "ai.disable.confirm_message": [
            .pt: "Novas análises IA não serão geradas até você ativar o recurso novamente.",
            .en: "New AI analyses will not be generated until you enable the feature again."
        ],
        "ai.disable.confirm_cta": [.pt: "Desativar", .en: "Disable"],
        "ai.source.paper": [.pt: "Paper científico", .en: "Research paper"],
        "ai.source.code": [.pt: "Código-fonte", .en: "Source code"],
        "ai.maintenance.title": [.pt: "Perspectiva IA em manutenção", .en: "AI Outlook is under maintenance"],
        "ai.maintenance.message": [
            .pt: "O recurso foi pausado temporariamente. Sua ativação fica salva e voltará quando a análise for liberada.",
            .en: "This feature is temporarily paused. Your activation is saved and will return when analysis is available."
        ],
        "ai.ftue.title": [.pt: "Antes de usar a Perspectiva IA", .en: "Before Using AI Outlook"],
        "ai.ftue.message": [
            .pt: "As previsões podem estar erradas, os dados da Yahoo podem atrasar ou falhar, e a análise não é recomendação de investimento. Use como apoio, não como decisão automática.",
            .en: "Forecasts can be wrong, Yahoo data may be delayed or incomplete, and this analysis is not investment advice. Use it as support, not as an automatic decision."
        ],
        "ai.error.generic": [
            .pt: "Não foi possível carregar a análise IA agora. Tente novamente em alguns instantes.",
            .en: "Could not load the AI analysis right now. Try again in a moment."
        ],
        "ai.error.network": [
            .pt: "Não conseguimos conectar agora. Verifique sua internet e tente novamente.",
            .en: "We could not connect right now. Check your internet and try again."
        ],
        "ai.error.timeout": [
            .pt: "A análise IA demorou mais que o esperado. Tente atualizar novamente em instantes.",
            .en: "The AI analysis took longer than expected. Try refreshing again in a moment."
        ],
        "ai.error.unavailable": [
            .pt: "A análise IA está temporariamente indisponível. Tente novamente em alguns minutos.",
            .en: "AI analysis is temporarily unavailable. Try again in a few minutes."
        ],
        "ai.error.not_found": [
            .pt: "Ainda não há dados suficientes para gerar a análise IA deste ativo.",
            .en: "There is not enough data to generate AI analysis for this ticker yet."
        ],
        "ai.error.busy": [
            .pt: "A análise IA está com muitas solicitações agora. Tente novamente em instantes.",
            .en: "AI analysis is handling many requests right now. Try again in a moment."
        ],
        "ai.target": [.pt: "Preço-alvo", .en: "Target"],
        "ai.confidence": [.pt: "Confiança", .en: "Confidence"],
        "ai.support": [.pt: "Suporte", .en: "Support"],
        "ai.resistance": [.pt: "Resistência", .en: "Resistance"],
        "ai.forecast_range": [.pt: "Faixa prevista", .en: "Forecast range"],
        "ai.risk": [.pt: "Risco", .en: "Risk"],
        "ai.drivers": [.pt: "Fatores", .en: "Drivers"],
        "ai.warnings": [.pt: "Avisos", .en: "Warnings"],
        "ai.warning.forecasts_probabilistic": [
            .pt: "As previsões são probabilísticas e podem estar erradas.",
            .en: "Forecasts are probabilistic and can be wrong."
        ],
        "ai.warning.not_investment_advice": [
            .pt: "Isto é apoio à decisão, não recomendação de investimento.",
            .en: "This is decision support, not investment advice."
        ],
        "ai.warning.yahoo_data": [
            .pt: "Os dados de candles do Yahoo podem estar atrasados ou incompletos.",
            .en: "Yahoo chart data may be delayed or incomplete."
        ],
        "ai.outlook.bullish": [.pt: "Alta", .en: "Bullish"],
        "ai.outlook.neutral": [.pt: "Neutro", .en: "Neutral"],
        "ai.outlook.bearish": [.pt: "Baixa", .en: "Bearish"],
        "ai.risk.low": [.pt: "Baixo", .en: "Low"],
        "ai.risk.medium": [.pt: "Médio", .en: "Medium"],
        "ai.risk.high": [.pt: "Alto", .en: "High"],
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
        "alert.percent_prices": [.pt: "Base %@ | Alvo %@", .en: "Base %@ | Target %@"],
        "alert.percent_missing_baseline": [
            .pt: "O preço base será definido na próxima cotação disponível.",
            .en: "The base price will be set from the next available quote."
        ],
        "alert.unsaved_title": [.pt: "Descartar alterações?", .en: "Discard changes?"],
        "alert.unsaved_edit_message": [
            .pt: "Este alerta tem alterações não salvas.",
            .en: "This alert has unsaved changes."
        ],
        "alert.unsaved_new_message": [
            .pt: "Este novo alerta ainda não foi salvo.",
            .en: "This new alert has not been saved yet."
        ],
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
