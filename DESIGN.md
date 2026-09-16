---
version: alpha
colors:
  background: '#0B1220'
  surface: '#142033'
  foreground: '#E7EEF7'
  primary: '#7CAEFF'
  positive: '#3DD6A0'
  negative: '#FF7B72'
  muted: '#9AAEC6'
  border: '#2B3B52'
  warning: '#F4C66A'
typography:
  sans:
    fontFamily: 'IBM Plex Sans, system-ui, sans-serif'
  mono:
    fontFamily: 'IBM Plex Mono, monospace'
rounded:
  DEFAULT: '10px'
  control: '6px'
spacing:
  unit: '4px'
components:
  ResearchPanel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.DEFAULT}"
  PositiveValue:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.positive}"
  NegativeValue:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.negative}"
  SecondaryLabel:
    backgroundColor: "{colors.background}"
    textColor: "{colors.muted}"
  WarningLabel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warning}"
  Separator:
    backgroundColor: "{colors.border}"
---

## Overview

A quiet financial research desk for a private investment team. Balanced density, one focal evidence panel per analysis page, explicit source and method context. Navigation describes research jobs rather than implementation. Dark theme only in V1. English UI; financial observations retain exchange-timezone context.

The signature is a persistent research context strip: instrument, observation time, currency, price basis and window remain legible beside evidence. No hero marketing, decorative gradients, glowing charts, or fake live status.

## Colors

The normative palette is the frontmatter above. Green/coral encode positive/negative changes; blue encodes selection and focus. Warning uses a separate amber role. Correlation uses a symmetric diverging scale; missing cells have an explicit neutral treatment. Text and signs supplement color.

## Typography

IBM Plex Sans for controls/body/headings; IBM Plex Mono for data. Base body 14–16px, headings 24–30px, primary price 32–40px. Tabular values align by decimal/right edge. Self-host fonts; do not block layout on network font requests.

## Layout

Desktop: 224px collapsible sidebar, 28px page padding, maximum 1600px content region, flexible twelve-column layout. Primary chart is visually dominant. Mobile under 768px uses a top navigation trigger, one column, prominent evidence before controls; landscape supports comparison tables without page-level horizontal overflow. Page owns vertical scrolling; large tables own only their local overflow.

## Elevation & Depth

Panels use subtle borders, not glow. Only floating overlays have a quiet shadow. Reserve all chart/loader geometry. Global scrollbars remain visible and tokenized.

## Shapes

Panels 10px radius, controls 6px. Compact, stable action dimensions. Thin separators divide related financial evidence.

## Components

Shared owners: research panel, metric, status/context strip, timeframe selector, searchable symbol combobox, tabs, buttons, fields, dialog, toast and chart adapter. Native tables for lookup. Authored Radix-compatible accessible overlays/selects; charts always include text summary and a data-table alternative.

Runtime ownership uses Model B: `frontend/src/styles/tokens.css` is the canonical runtime token source; this document records the accepted values and explains their use. `scripts/check_design_tokens.py` prevents drift. Plotly reads the same CSS custom properties through its adapter. No independently maintained chart palette.

| Design path | Runtime target | Consumers |
|---|---|---|
| colors.background / foreground | --bg / --fg | Page, body text, chart canvas |
| colors.surface | --surface | Research panels, overlays |
| colors.primary | --primary | Actions, focus, selected marks |
| colors.positive / negative | --positive / --negative | Signed values, return marks |
| colors.muted / border / warning | --muted / --border / --warning | Labels, separators, data status |
| rounded.DEFAULT / control | --radius / --control-radius | Panels / controls |
| spacing.unit | --space | Shared spacing scale |
| typography.sans / mono | IBM Plex Sans / IBM Plex Mono | Interface / numerical values |

## Do's and Don'ts

- Preserve stale evidence during refresh; never disguise demo values as live.
- Display fraction/percentage, currency, sample count and timeframe consistently.
- Use literal data marks, source dates and method notes rather than atmosphere.
- Generated concept direction accepted to continue on 2026-09-15; see docs/concepts/README.md for exact scope and required corrections. Preserve reading order and mobile continuation in code. Concepts are references, not application screenshots.
