# Recommended commercial model

Status: product proposal; prices not yet set

## Product split

Code Browser should use a three-part model:

1. **Public MIT core and Provider Plugin SDK** — local browsing, source reading, and user-controlled provider connections remain inspectable and extensible.
2. **Official subscription** — signed desktop/mobile distribution, managed updates, encrypted history/sync, account features, premium workflows, support, team policy, and access to the managed inference service.
3. **Managed inference usage** — included monthly credits plus capped prepaid or metered overage when GK Works pays the upstream provider cost.

For a third-party/BYOK plugin, the user pays that provider directly. GK Works should not add inference usage charges because it does not supply the tokens and cannot independently trust plugin-reported counts. The official-app subscription can still apply to subscription features.

For GK Works managed models, the customer pays the subscription plus usage above the included allowance. Keep raw provider input/output counts internally, but sell clearly defined product credits if provider economics differ by model.

## MIT constraint

The current public client has already been released under MIT. MIT permits forks, self-builds, redistribution, modification, and commercial use. Existing grants cannot practically be withdrawn.

Therefore “every use of Code Browser requires a subscription” is not enforceable for the MIT source. A sustainable promise is:

- the community can continue using or building the MIT core;
- official GK Works services and subscription features require an account;
- official binaries may be sold, but others may still build the MIT source;
- trademarks distinguish official builds from forks;
- private managed-service code, credentials, pricing, and operations remain outside the public repository.

If strict subscription-only application access becomes essential, GK Works would need a proprietary future shell or edition around the MIT core. Earlier MIT versions would remain available, so this should be justified by customer value rather than treated as a technical lockout.

## Suggested plans

Do not set dollar prices until provider approval and measured unit economics exist. Define entitlements first:

| Plan | App/service entitlement | Inference |
|---|---|---|
| Community | MIT self-hosted core, local state, public plugins | BYOK/direct provider only |
| Personal | Official builds, updates, encrypted sync/history, premium workflows, support | Included managed credits; capped paid overage |
| Team | Personal features plus organization budgets, policy, audit, and administration | Pooled included credits; administrator-controlled overage |

Use a time-limited Personal trial rather than an unlimited anonymous inference allowance. Anonymous inference is easily abused and spends GK Works money before identity is established.

## Billing rules to decide before launch

- monthly versus annual subscription;
- included credit amount per plan;
- prepaid overage versus capped postpaid usage;
- model-specific credit weights and price-version changes;
- whether failed, cancelled, disconnected, and `metering_unknown` requests consume credits;
- credit expiration, rollover, refunds, taxes, disputes, and account cancellation;
- spending alerts, hard caps, team budgets, and administrator approval;
- App Store and Play Store packaging and payment-channel requirements;
- plugin marketplace fees or revenue share, if a marketplace is introduced.

The safest initial paid launch is a subscription with included credits and opt-in prepaid overage. Avoid unlimited plans and uncapped postpaid inference until fraud, reconciliation, refunds, and provider limits are proven.
