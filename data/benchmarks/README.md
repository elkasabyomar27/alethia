# Benchmark source and private holdout

`development.json` contains 120 agent-authored development candidates in 40 trilingual intent groups (40 English, 40 Modern Standard Arabic, 40 Egyptian Arabic). These are seed references, not human review attestations. Reviews remain in the ignored local database.

The owner's 30 reserved candidates remain in **ignored `reserved.local.json`**, preserving their question IDs, groups, evidence and references. The default application loader merges this optional file after checking its dataset identity, test-only labels and cross-split isolation. Without it, a public clone runs with 120 development candidates and zero available held-out candidates. It does not generate replacement test questions or pretend a held-out test was run.

Keep reserved groups out of tuning. Do not upload the private file, review database, frozen raw snapshots or full local reports. Back up private evaluation material separately. Public pilot aggregates describe the historical experiment configuration, not the count of questions shipped in this repository.
