# Decision 002: Evidence-led deep code reading

## Decision and outcome

Add a distinct Deep Read mode for an open source file. It uses one provider request to trace the target and a bounded set of related source excerpts, while keeping the editor and source navigation central to the experience.

## Evidence and assumptions

- User request: Code Browser needs a deeper reading mode beyond summary and explanation.
- Existing behavior: generated file and symbol references already navigate back to visible source.
- Product constraint: Code Browser should remain file-browser-first, lightweight, and explicit about model usage.
- Assumption to validate: readers benefit more from evidence citations and reading checkpoints than from a longer free-form explanation.

## Chosen direction

- One explicit user action; never starts automatically when a file or directory opens.
- One model request, not a hidden multi-pass agent loop.
- Line-numbered target plus a source inventory and at most eight relevant excerpts.
- A 55,000-character target budget and 35,000-character related-context budget, leaving room for a substantial answer in the 32K context window.
- Required fact, inference, and unknown labels with clickable `path:line` evidence.
- Support both Japanese and English; PDF uses a document-specific deep-reading prompt.

## Alternatives considered

- Reuse Explain with a longer prompt: lower UI cost, but the user cannot predict the deeper cost or output contract.
- Multi-agent recursive exploration: potentially broader, but higher cost, slower completion, and weaker control over what source leaves the machine.
- Send the whole repository: simpler selection logic, but unsafe for context limits, cost, and accidental disclosure.

## Validation

- API tests verify numbered target lines, related-file selection, and the evidence-led prompt contract.
- App-shell tests verify the localized action is shipped.
- Next checkpoint: observe whether users open cited lines and whether the selected related files match their expectations.
