# Roadmap

Where shiftsim is headed. This is a living document; concrete work lives in
GitHub issues (tagged `roadmap` for the big items).

## Now — get it in front of the crew

- **Deploy to `corvopi-live`** behind nginx so anyone on the crew can open it in
  a browser and compare techniques. Spec: [`docs/specs/deploy-corvopi-live.md`](specs/deploy-corvopi-live.md).
  This is the first feature.

## Next — make comparisons richer

- **Sync-start toggle** — force all boats onto the same first tack so a
  comparison isolates the strategy from the starting-side advantage.
- **Ladder-gap readout** — the gap between any two boats over time, in the panel.
- **Save / share a scenario** — a permalink that encodes the full config so crew
  can send each other exact situations ("what would you do here?").
- **Spatial wind field** — wind that varies by position, not just time, to study
  "which side of the course pays". The engine interface is already spatial-ready.

## Later — depth

- **Import real polars** in the UI (ORC/VPP CSV) so crew can model their own boat.
- **Current / tide** as a vector field added to boat motion.
- **More strategies** — leverage/loss-minimisation, fleet-relative covering,
  laylines-only, and user-authored rules.
- **Replay scrubbing of the ladder-gain chart** alongside the course view.

## Guiding principles

- Stays correct and trustworthy (the tactical regression tests must hold).
- Stays zero-install where possible (pure stdlib engine).
- Every new field documents itself (`web/docs.html` + tooltips, enforced by CI).
