# BOLT #11: Invoice Protocol for Lightning Payments

## Requirements

A writer:
  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.
  - MUST set `payment_secret` to a fresh, random value.

## Rationale

The `payment_secret` prevents intermediate nodes from probing the
payment.
