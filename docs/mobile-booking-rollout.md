# Mobile booking rollout

## Required deployment secrets

- `PAYME_ENABLED`, `PAYME_MERCHANT_ID`, `PAYME_KEY`, `PAYME_CHECKOUT_URL`
- `CLICK_ENABLED`, `CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID`, `CLICK_SECRET_KEY`, `CLICK_CHECKOUT_URL`
- `STRIPE_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

Keep every provider disabled until its credentials and callback registration are
verified in that provider's sandbox. Stripe must remain disabled in production
until a supported-jurisdiction merchant account and legal approval are in place.

## Callback registration

- Payme: `/api/v1/payment-webhooks/payme/`
- Click prepare: `/api/v1/payment-webhooks/click/prepare/`
- Click complete: `/api/v1/payment-webhooks/click/complete/`
- Stripe: `/api/v1/payment-webhooks/stripe/`

The common browser/app return is
`https://i-deal.uz/payment-return?checkout=<opaque-token>`. A return never proves
payment; Mobile polls the authenticated booking endpoint after returning.

## Release order

1. Apply schema migrations and deploy booking services.
2. Register callbacks and enable the Django-Q cluster schedules.
3. Deploy the association files and browser fallback.
4. Release Mobile with `MOBILE_BOOKING_CHECKOUT_ENABLED` disabled.
5. Validate Payme and Click on Android and iOS, then enable them independently.
6. Enable Stripe only after account and legal readiness.

Before the app-link deployment, replace every Android fingerprint placeholder
in Frontend's `public/.well-known/assetlinks.json` with the release/app-signing
SHA-256 fingerprint for that flavor.
