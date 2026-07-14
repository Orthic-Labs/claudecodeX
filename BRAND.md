# ANYCLAUDE identity

## Brand truth

ANYCLAUDE helps developers keep subscription Claude open while running a second, isolated Claude session on another Anthropic-compatible model, and should feel like the missing second route rather than a replacement Claude brand.

## Signature mechanism

The identity uses a **split route**: neutral `ANY` accepts the provider choice; Claude terracotta `CLAUDE` preserves the recognizable interface destination; a thin line moves from an open point to an arrow. Product proof uses a second split: subscription Claude on one side, anyclaude on the other, both visibly active on one desktop.

## Wordmark

- Primary asset: `assets/anyclaude-wordmark.svg`
- Display construction: Tanker, converted to SVG outlines; the font file is not distributed
- `ANY`: warm white `#F5F2EA`
- `CLAUDE`: Claude terracotta `#D97757`
- Base: route black `#0B0D10`
- Clearspace: at least the width of the `A` counter on every side
- Minimum width: 240px for the full route lockup; below that, omit the route line rather than shrinking it into noise

GitHub README pages cannot load a project webfont stylesheet. The primary wordmark therefore uses Tanker glyphs converted to SVG paths. It is a resolution-independent vector asset, not a raster screenshot, and it renders consistently without shipping or remotely loading the font. Do not replace the paths with SVG `<text>` or styled Markdown; either can fall back to a generic font on GitHub.

Do not recolor `CLAUDE` to a generic technology blue or move terracotta onto `ANY`. Do not add gradients, glow, robot/brain imagery, or a separate generic AI symbol.

## Color roles

| Token | Hex | Role | Contrast on route black |
|---|---|---|---:|
| Route black | `#0B0D10` | Wordmark field, technical diagrams | — |
| Any white | `#F5F2EA` | Modifier, primary text | 17.39:1 |
| Claude terracotta | `#D97757` | Claude name, route destination, active proof | 6.23:1 |
| Route graphite | `#252A31` | Dividers and inactive route lines | Decorative only |

Terracotta is scarce and semantic: it identifies Claude or the active route. White carries explanation and provider-neutral content.

## Typography

- Display/wordmark: Tanker Regular
- Documentation/UI: system sans (`-apple-system`, BlinkMacSystemFont, `Segoe UI`, sans-serif)
- Commands/data: system monospace (`SFMono-Regular`, Consolas, monospace)

Tanker is for the name and short display statements only. It must not replace readable body or command text.

## Composition and imagery

- Lead with one-desktop/two-session compositions; the operating-system taskbar or Dock should be visible when it proves simultaneity.
- Prefer split-screen, input-to-output, and source-to-route compositions.
- Use real Claude Code/Desktop screenshots as proof.
- Keep diagrams linear: interface → local proxy → provider.
- Avoid abstract AI renders, decorative gradients, card grids, and fake terminal output.

## Voice

Direct, slightly defiant, and operational. Lead with **Keep Claude. Add another one.** Then prove the simultaneous-session behavior before explaining the proxy. State what is verified, what is untested, what mutates the machine, and what consumes a paid request. Avoid “seamless,” “unlock,” “revolutionary,” and claims that every Anthropic-compatible provider is proven.

## Asset provenance

The current wordmark was outlined from the project's existing Tanker font resource, so GitHub renders the intended letterforms without redistributing an editable font file. The side-by-side screenshot is real product evidence supplied by the project owner; it includes the Windows taskbar to prove both sessions share one desktop.
