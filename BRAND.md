# CLAUDECODEX identity

## Brand truth

CLAUDECODEX helps developers keep subscription Claude open while running a second, isolated Claude session on another Anthropic-compatible model, and should feel like the missing second route rather than a replacement Claude brand.

## Signature mechanism

The identity uses a **split route**: neutral `ANY` accepts the provider choice; Claude terracotta `CLAUDE` preserves the recognizable interface destination; a thin line moves from an open point to an arrow. Product proof uses a second split: subscription Claude on one side, ClaudeCodeX on the other, both visibly active on one desktop.

## Wordmark

- Primary asset: `assets/ClaudeCodeX-wordmark.svg`
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
| Route black | `#0B0D10` | Wordmark field, technical diagrams | N/A |
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

Direct, explicit, and operational. Lead with the literal product behavior: **Run two Claude Desktop instances simultaneously.** Name the provider in each instance and state that both stay open on one computer before explaining the proxy. Do not substitute a clever slogan for those facts. Never use em dashes. State what is verified, what is untested, what mutates the machine, and what consumes a paid request. Avoid “seamless,” “unlock,” “revolutionary,” and claims that every Anthropic-compatible provider is proven.

## Preview cards

Two cards for two slots. Both render from HTML with headless Chrome at an exact window size. Both show the same real two-session desktop as proof and end the route line in terracotta.

**README hero**: `assets/social-preview.png` (1280x1144), embedded at the top of the README. Text band (wordmark, claim, provider line) stacked above the full uncropped screenshot. Source `assets/social-preview.html`.

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=old --disable-gpu \
  --screenshot=assets/social-preview.png --window-size=1280,1144 --hide-scrollbars \
  "file://$PWD/assets/social-preview.html"
```

**Link-share card**: `assets/link-card.png` (1280x640, 2:1), the image GitHub and social platforms show when the repo is linked off-site. Text left, the whole two-session desktop framed on the right, no crop. Source `assets/link-card.html`. The 2:1 slot center-crops anything taller, which is why the tall hero cannot serve it.

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=old --disable-gpu \
  --screenshot=assets/link-card.png --window-size=1280,640 --hide-scrollbars \
  "file://$PWD/assets/link-card.html"
```

On the link card the screenshot is scaled down until its session text is texture, not readable content. Do not crop either card into a single window: the two windows and the taskbar are the entire claim. GitHub has no API for the link-share slot; upload `link-card.png` at **Settings > General > Social preview** after changing it.

## Asset provenance

The current wordmark was outlined from the project's existing Tanker font resource, so GitHub renders the intended letterforms without redistributing an editable font file. The side-by-side screenshot is real product evidence supplied by the project owner; it includes the Windows taskbar to prove both sessions share one desktop.
