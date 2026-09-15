# Lan Anh Avenue Decision Twin v0.1

## MVP question

Can Synapse Real-World estimate how aggregate LAA buyer choice changes when **price × payment plan × commute × product type** changes, while preserving historical validity and outside options?

## Canonical decision chain

```text
lead -> qualification -> consideration -> site tour -> negotiation -> booking/contract/lost
                     \-> reason observations
                     \-> choice set at time T
```

## Required first data contracts

1. pseudonymous `party_id` and `household_id`;
2. versioned units/inventory;
3. versioned offers/payment plans;
4. interaction timestamps/channels;
5. structured reasons (motivator/objection + confidence/evidence);
6. site-tour events;
7. verified booking/contract/cancel/lost outcomes;
8. choice alternatives including outside options;
9. commute/accessibility features with observation method/time;
10. campaign/creative identifiers for later real-world experiments.

## First scenario families

- **S01 Price elasticity**: ±3–5% effective price.
- **S02 Payment cash-flow**: same nominal net price, different near-term burden.
- **S03 Commute perception**: measured vs perceived travel time.
- **S04 Product substitution**: migration between product families and outside options.

## Model progression

`transparent utility baseline -> multinomial logit -> mixed/hierarchical logit -> calibrated ML challenger`

Models are evaluated on temporal holdout with log-loss/Brier/calibration and aggregate predicted-vs-actual choice/funnel outcomes.

## v0.1 fixture warning

The demo price/payment/commute values in `projects/laa/world.py` are intentionally synthetic placeholders. They are not production LAA facts and must not be used for business decisions. Real values enter only through versioned source adapters with provenance.
