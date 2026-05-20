# Empirical-probe test assets

Two 96×96 PNG images of single Arabic digits ("3" and "7"), black on white.
Used by `scripts/sync_model_registry.py probe` to verify that a model
claiming `vision_capable=true` can actually process image input.

The model is asked: "What single digit appears in this image? Reply with
only the digit, no other text." A model passes iff its response contains
the expected digit and is short (≤ 30 chars). Both digits must succeed
for the registry's `vision_capable` flag to be set to `true`.

Random-luck false-positive rate: 1/100 (one in ten chance per digit; both
must hit).

These files ship in the repo so probes work at install time without
requiring PIL or font availability on the user's machine.
