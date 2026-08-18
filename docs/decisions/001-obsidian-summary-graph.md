# Decision 001: Obsidian-style summary graph

## Decision and outcome

Replace the layered relationship boxes in Summary results with a compact force-directed code knowledge graph. The graph should help readers identify important files and symbols, distinguish structural roles, and navigate back to source without displacing the written summary.

## Evidence and assumptions

- Existing behavior: Summary already requests evidence-based relationship edges and renders a clickable local SVG.
- User request: an Obsidian-like view covering file structure, functions, classes, and UI/UX would make relationships easier to understand.
- Assumption to validate: node type and centrality are more useful than a strict left-to-right flow for repository comprehension.
- Constraint: no external graph library, no additional network request, and usable behavior in the resizable desktop Assistant and mobile panel.

## Chosen direction

- Deterministic force-directed layout generated locally.
- Typed nodes: file, function, class, UI, data, external, and symbol.
- Node size reflects degree; color reflects type.
- Existing click and keyboard navigation remains available for source-backed nodes.
- The old three-column edge format remains accepted for cached or third-party responses.
- Prompts prohibit invented UI elements and unsupported relationships.

## Alternatives considered

- Keep the layered flowchart: clearer direction, but weak for cross-cutting and cyclic relationships.
- Add a full graph library: richer interaction, but adds weight and supply-chain surface to a deliberately lightweight tool.

## Validation

- Automated checks cover the typed prompt contract and app-shell assets.
- Manual validation should test a backend file, a class-heavy file, and a UI file on desktop and mobile.
- Success signal: users can identify the most connected element and open a relevant source node without reading instructions.
