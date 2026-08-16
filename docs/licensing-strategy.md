# Licensing Strategy for Free and Paid Plans

Status: recommended product policy; obtain legal review before commercial launch  
Date: 2026-08-16

## Current state

The public Code Browser repository is licensed under the MIT License. MIT permits anyone to use, copy, modify, publish, distribute, sublicense, and sell copies, provided the copyright and license notice is preserved.

A paid Code Browser plan is compatible with MIT. The software license and the hosted service contract are separate:

- MIT grants rights to the public source code.
- Product Terms govern accounts, hosted inference, token or credit allowances, billing, acceptable use, service availability, and support.
- A Privacy Policy governs source-code transit, account data, payment metadata, retention, subprocessors, and deletion.
- Trademark rules govern the product name and logo; MIT does not grant trademark rights.

## Recommended structure

### 1. Public local client: MIT

Keep this repository and the local-first file browser under MIT. This supports adoption, inspection, self-hosting, community contributions, and the project's File Browser-first positioning.

The public client may include the UI for sign-in, plan display, remaining allowance, and calls to the commercial API. Those client-side integrations remain MIT and may be forked.

### 2. Commercial inference and billing service: proprietary

Put the multi-tenant Ollama wrapper, identity service, abuse controls, usage ledger, price catalog, Stripe integration, reconciliation jobs, and operational configuration in a separate private repository and deploy them as a hosted service.

Customers pay for the service—not for permission to execute the MIT client. Paid value may include:

- managed Ollama or other model inference;
- usage credits above the anonymous or registered free allowance;
- encrypted synchronization and history;
- team accounts, policy, audit, and administration;
- managed updates, support, reliability, and compliance features.

The service Terms should state that credits are service entitlements, define expiration/refund rules, and explain whether charges use raw input/output tokens or normalized product credits.

### 3. Brand and distribution

Adopt a separate trademark policy for the official product name, logo, domains, and “official” builds. Forks may comply with MIT while still being prohibited from implying endorsement or using protected branding beyond nominative use.

Before a paid launch, consider a distinctive primary brand that does not depend on the Ollama trademark. Continue the existing statement that the project is not affiliated with or endorsed by Ollama.

## What MIT does and does not protect

MIT allows GK Works to charge for binaries, subscriptions, hosted inference, support, and enterprise features. It also allows a third party to:

- fork the client;
- remove the commercial API integration;
- redistribute or sell a modified build;
- host the MIT code as part of another service;
- compete using code already released under MIT, while preserving the required notice.

Changing the license on future releases cannot practically retract MIT rights already granted for earlier published versions. Keep this in mind before placing commercially sensitive server code in the public repository.

MIT does not grant access to GK Works infrastructure, Ollama credentials, customer data, private repositories, domains, support, or trademarks.

## Alternatives considered

| Option | Paid plan compatibility | Competitor protection | Open source? | Assessment |
|---|---|---|---|---|
| MIT client + private service | Yes | Protects private backend, not client forks | Yes, for client | Recommended now |
| AGPL client/server + commercial license | Yes | Requires source offer for modified network deployments, but does not prohibit commercial hosting | Yes | Consider only if the server is intentionally public and contributor rights are controlled |
| Elastic License 2.0 | Yes | Prohibits offering substantial functionality as a hosted/managed service | No, source-available | Stronger anti-SaaS protection but weakens OSS positioning and ecosystem compatibility |
| Business Source License 1.1 | Yes | Production use can require a commercial license until the change date | No until conversion | Useful for delayed-open server code, but more complex for users and contributors |
| Fully proprietary application | Yes | Strongest source control | No | Conflicts with current public/marketing strategy and cannot revoke prior MIT releases |

Elastic License 2.0 and Business Source License 1.1 are source-available rather than OSI open-source licenses. Do not describe a project using them as “open source.”

## Why not change this repository now

The paid differentiator is the metered hosted service described in `metered-ollama-wrapper.md`, not the local browser. Changing the client away from MIT would add contributor and adoption friction without protecting the private inference key, billing ledger, provider agreement, or operational controls.

If the company later publishes the wrapper, make that a separate licensing decision. AGPL plus a commercial license is the clearest open-source dual-license candidate; an anti-hosting source-available license is an alternative only if the company accepts that the wrapper will not be open source.

## Required commercial documents

Before accepting payment, prepare documents separate from `LICENSE`:

1. Terms of Service covering account eligibility, free and paid allowances, acceptable use, suspension, model availability, renewals, cancellation, refunds, taxes, liability, and dispute terms.
2. Privacy Policy covering source-code processing, Ollama and payment providers as subprocessors, retention, deletion, security, international transfers, and user rights.
3. Pricing and Credit Policy defining measurement, model weights/rates, rounding, failed requests, disconnects, expiration, refunds, and usage disputes.
4. Trademark Policy for official builds, naming, logos, and fork attribution.
5. Enterprise DPA and security exhibit if customer source code or personal data is processed for business customers.
6. Third-Party Notices for dependencies and bundled assets in desktop, Android, or other binary distributions.

## Contributor policy

All current Git history is authored under the existing GK Works identity, but future external contributions can complicate relicensing. Before accepting them:

- require a Developer Certificate of Origin or a Contributor License Agreement;
- document whether contributors grant GK Works the right to offer the work under commercial terms;
- require sign-off in pull requests;
- keep a machine-readable dependency/license inventory and review new dependencies before release.

A DCO alone confirms contribution rights but does not necessarily grant broad relicensing rights. Use a lawyer-reviewed CLA if future dual licensing is a serious possibility.

## Immediate decisions

1. Keep the current public repository under MIT.
2. Keep the metered inference/billing wrapper in a separate private repository.
3. Sell hosted service and credits, not an exclusive license to the MIT client.
4. Do not publish API keys, price enforcement, fraud rules, or billing credentials in the client.
5. Obtain written Ollama permission for the intended multi-tenant commercial use before launch.
6. Use `GK Works, Inc` as the copyright holder in `LICENSE` and release notices.
7. Have counsel review the Terms, Privacy Policy, provider agreement, and final licensing structure before collecting payments.

## References

- MIT License, Open Source Initiative: https://opensource.org/license/mit
- Open Source Definition, Open Source Initiative: https://opensource.org/osd
- Elastic License 2.0: https://www.elastic.co/licensing/elastic-license
- Business Source License 1.1: https://mariadb.com/bsl11/
- Ollama Terms of Service: https://ollama.com/terms
