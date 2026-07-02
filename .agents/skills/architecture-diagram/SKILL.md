---
name: architecture-diagram
description: Design polished architecture diagrams, system overviews, platform maps, solution blueprints, technical landscape slides, and layered capability views. Use when creating or revising an architecture visual in HTML, SVG, slides, images, or other visual formats. Default to a connector-free composition with no arrows or relationship lines; communicate structure through containment, aligned layers, grouping, spacing, labels, and restrained color.
---

# Architecture Diagram

Create architecture diagrams that read through hierarchy and spatial organization rather than a web of connectors.

## Non-negotiable default

- Do not draw arrows.
- Do not draw connector lines, leader lines, flow lines, dependency lines, dotted paths, or decorative lines that could be mistaken for relationships.
- Do not use arrow characters or directional chevrons between components.
- Do not reserve empty corridors for imaginary connectors.
- Treat any visible connector as a defect unless the user explicitly requires connections.
- If the user explicitly requests connections, first offer a connector-free alternative. Add only the minimum requested connections when they remain necessary.

## Communicate relationships without lines

Use these visual signals, in priority order:

1. **Containment:** Put related components inside a clearly titled parent region.
2. **Vertical hierarchy:** Arrange broad concerns at the top and foundational concerns at the bottom.
3. **Columns or swimlanes:** Use columns for peer domains, channels, products, environments, or actors.
4. **Proximity:** Keep related items close and separate unrelated groups with generous whitespace.
5. **Alignment:** Align peers to a shared grid and keep their dimensions consistent.
6. **Color families:** Give each domain one restrained tint; use color consistently, not decoratively.
7. **Numbering:** When order matters, use small step numbers or stage labels instead of arrows.
8. **Short captions:** State the relationship in a group subtitle when spatial placement alone is insufficient.

Never imply a false relationship merely to make the composition symmetrical.

## Choose one composition

Select the simplest pattern that matches the content:

### Layered stack

Use for systems with clear tiers. Create 3–6 full-width horizontal bands. Place peer cards inside each band.

Typical order:

- Experience / channels
- Business capabilities / applications
- Shared services / integration
- Data / intelligence
- Platform / infrastructure
- Governance / security as a side rail or quiet cross-cutting band

### Domain columns

Use for business domains or product families. Create 3–5 equal columns, each containing a short vertical stack. Put shared foundations in one full-width band below the columns.

### Core and surrounding domains

Use only when one genuine platform or product is central. Place the core in a large central panel and arrange surrounding domains as separate nearby cards. Use distance, headings, and color—not radial lines—to show association.

### Nested platform map

Use for ownership or deployment boundaries. Nest components inside 2–3 levels of containers. Avoid excessive nesting and never place tiny text inside deeply nested boxes.

Do not mix several composition patterns on one canvas.

## Build the hierarchy

1. Extract the title, scope, audiences, domains, components, and true parent-child relationships.
2. Remove duplicate concepts and collapse low-value implementation details.
3. Limit the top level to 3–7 groups.
4. Limit each group to 2–6 child components.
5. Assign every component exactly one primary visual home. Repeat an item only when the repeated label is explicitly marked as shared.
6. Choose a single composition pattern.
7. Place parent regions before child cards.
8. Verify the reading order without relying on connectors.
9. Add concise labels and optional one-line subtitles.
10. Apply restrained styling only after the structure is correct.

When the source material describes many point-to-point interactions, abstract them into a shared layer such as “Integration & APIs,” “Event Backbone,” or “Data Exchange” rather than drawing one line per interaction.

## Visual system

- Use one clear title and, when useful, one short subtitle.
- Use a consistent spacing unit and generous outer margins.
- Use a 12-column or similarly regular grid.
- Keep peer cards equal in width, height, padding, corner radius, and heading position.
- Use 3–6 layers and no more than 7 top-level groups.
- Use one neutral canvas, one primary accent, and no more than 3–5 restrained domain tints.
- Ensure text has strong contrast; do not rely on color alone to encode meaning.
- Use subtle borders or soft shadows, not both heavily.
- Keep icons optional, small, and stylistically consistent. Never use icons as substitutes for labels.
- Prefer short noun phrases of 1–4 words. Keep descriptions to one line when possible.
- Make the visual hierarchy obvious at thumbnail size: title, group headings, then component labels.

## Avoid

- Spiderweb, flowchart, circuit-board, or subway-map layouts.
- Crossing lines, curved arrows, bidirectional arrows, and arrows entering container borders.
- Decorative strokes between cards.
- Tiny labels floating in whitespace.
- More than three levels of visible nesting.
- Unequal gaps, arbitrary card sizes, or misaligned baselines.
- Excessive gradients, glow, glass effects, 3D perspective, or ornamental backgrounds.
- A separate box for every noun in the source.
- Legends that are needed only because the color system is too complex.

## Special cases

### Process or data flow

Convert the flow into numbered stages arranged left-to-right or top-to-bottom. Use large stage numbers and whitespace between stages. Do not connect stages.

### Cross-cutting concerns

Show security, governance, observability, and operations as a side rail, top cap, or bottom foundation. Do not draw a line from each concern to every component.

### Shared services

Place shared services in one clearly labeled full-width region adjacent to the consumers. Do not duplicate them inside every domain.

### Required connection semantics

If exact network, sequence, or dependency semantics are the main subject and omitting connectors would make the diagram inaccurate:

1. Tell the user that the request conflicts with the connector-free default.
2. Prefer a matrix, numbered interaction table, or paired “source / relationship / target” list beside the architecture view.
3. If connectors are still explicitly required, use only direct orthogonal connectors, one semantic style, no crossings, and a separate detailed view rather than cluttering the overview.

## Quality gate

Before delivering, verify every item:

- [ ] There are no arrows, arrowheads, connector lines, relationship strokes, or directional chevrons.
- [ ] The diagram remains understandable in grayscale.
- [ ] The title, groups, and components form three visibly distinct text levels.
- [ ] Every component has one unambiguous parent or region.
- [ ] Peers align to a consistent grid and use consistent dimensions.
- [ ] Whitespace clearly separates unrelated groups.
- [ ] No group is overcrowded; details have been consolidated or moved to a secondary view.
- [ ] The reading order is obvious without explanation.
- [ ] Cross-cutting concerns use a band or rail rather than repeated links.
- [ ] The final view is accurate, balanced, and legible at its intended display size.

If any check fails, revise the hierarchy or grouping before adding visual decoration.
