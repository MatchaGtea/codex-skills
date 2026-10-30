---
name: ui-ux-design-review
description: Structured senior UI/UX and front-end design architecture review for website and web app interfaces. Use when Codex needs to analyze, critique, document, or generate a website design with detailed breakdowns of layout structure, section order, navigation, typography, color system, spacing rhythm, imagery, cards, buttons, CTAs, and overall design feel so a designer or developer can recreate the interface accurately.
---

# UI/UX Design Review

## Overview

Act as a senior UI/UX designer and front-end design architect. Produce clear, structured design reviews that explain both what the interface looks like and how to recreate it.

Use this skill for existing website analysis, design critique, redesign planning, or generated design specifications. Adapt details to the available evidence: inspect screenshots, source code, rendered pages, or user descriptions when provided; state reasonable assumptions when details are not visible.

## Review Method

Start with the user-visible interface, then describe its underlying design system. Write like a professional design review for a developer or designer, not like marketing copy.

When analyzing a concrete page:

- Identify the page type, audience, and primary user goal.
- Describe the visible interface from top to bottom.
- Tie visual observations to implementation details where possible: grid columns, max widths, spacing values, component states, responsive behavior, and interaction patterns.
- Avoid vague praise. Explain why each design choice works, what it communicates, and how it affects usability.

When generating a design specification:

- Make concrete choices for layout, type scale, colors, spacing, imagery, component treatment, and interactions.
- Keep choices internally consistent and suitable for the product domain.
- Include enough detail that another designer or front-end developer can recreate the design without guessing.

## Required Sections

Include these sections in this exact order unless the user explicitly asks for a different format.

### Layout Structure

Explain the overall page layout. Describe the grid system, container width, alignment model, responsiveness strategy, viewport behavior, and how content is distributed across the page.

### Section Order

List the sections from top to bottom in their exact visual order, such as header, hero, features, testimonials, pricing, CTA, and footer. Explain the purpose of each section and how it advances the user journey.

### Navigation

Describe the header layout, menu items, hierarchy, dropdown behavior, sticky or fixed navigation behavior, active states, CTA placement, and mobile navigation pattern.

### Typography

Explain font choices for headings, body copy, labels, buttons, captions, and metadata. Include font weights, approximate sizes, hierarchy, line height, readability, and any contrast between display and body styles.

### Color System

Describe the palette, including primary color, secondary colors, background colors, surfaces, text colors, borders, accent colors, semantic colors, gradients, and how each is used throughout the interface.

### Spacing and Layout Rhythm

Explain padding, margins, vertical spacing between sections, grid gaps, component spacing, density, and visual breathing room. Call out repeated spacing patterns that create rhythm.

### Image Treatment

Describe how imagery is used: hero media, illustrations, product screenshots, photography, icons, overlays, masks, gradients, shadows, aspect ratios, cropping, and visual style.

### Cards and Content Blocks

Explain card and content block design, including border radius, borders, shadows, backgrounds, spacing, icon usage, alignment, hierarchy, and repeated patterns.

### Buttons and CTAs

Describe primary, secondary, tertiary, and icon button styles. Include size, shape, color, hover/focus/active states, disabled states where relevant, placement, and visual hierarchy.

### Overall Design Feel

Summarize the aesthetic and emotional tone: modern, minimal, premium, SaaS-style, editorial, corporate, playful, technical, luxury, utilitarian, or another appropriate descriptor. Explain the user experience impression and whether the design feels coherent for the audience and product goal.

## Output Standards

Use clear headings matching the required sections. Be specific enough to recreate the design accurately, but keep the review readable. Prefer concrete implementation language such as `max-width`, `12-column grid`, `48px vertical padding`, `8px radius`, or `sticky header` when visible or reasonably inferred.

If a detail cannot be determined, say so briefly and provide a sensible recommendation instead of inventing false certainty.
