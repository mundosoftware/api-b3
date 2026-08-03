//
//  OneSignalPushSubscriptionObserver.swift
//  Trade Altert
//
//  Created by Codex on 02/08/26.
//

import Foundation
import OneSignalFramework

final class OneSignalPushSubscriptionObserver: NSObject, OSPushSubscriptionObserver {
    private let onSubscribed: () -> Void
    private var hasReportedServerSubscription = false

    init(onSubscribed: @escaping () -> Void) {
        self.onSubscribed = onSubscribed
    }

    func onPushSubscriptionDidChange(state: OSPushSubscriptionChangedState) {
        evaluate(subscriptionId: state.current.id)
    }

    func evaluate(subscriptionId: String?) {
        guard
            !hasReportedServerSubscription,
            let subscriptionId,
            !subscriptionId.isEmpty,
            !subscriptionId.hasPrefix("local-")
        else {
            return
        }

        hasReportedServerSubscription = true
        DispatchQueue.main.async {
            self.onSubscribed()
        }
    }
}
