# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before any UI task, read:

- `../docs/product/PRODUCT_UX_MASTER_SPECIFICATION.md`;
- `UI_UX_WORKFLOW.md`;
- the relevant `../docs/product/UI_ACCEPTANCE.md` scenario;
- the relevant approved image in `../docs/design/reference/` when one exists.

## Design-first rule

Do not start a substantial visual change from code alone.

If the task changes layout, hierarchy, navigation, interaction, density, visual language, or a full workflow and there is no current approved visual target, use the Product Design workflow first and establish a visual target before implementation.

If an approved reference already exists, treat it as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content and hierarchy. Do not improvise a different design because it is easier to code.

A local bug fix may be implemented without a new mock only when it does not change the intended interaction or visual hierarchy.

## UX before components

Before implementation, state in the task notes:

1. the user's goal;
2. the primary path through the screen;
3. the primary action;
4. required empty/loading/error/partial-data states;
5. what must remain visible while the user works;
6. which actions can alter, hide, exclude or delete data.

Do not redesign a screen around the component library. Components serve the approved workflow, not the reverse.

## Visual quality gate

A UI task is not complete when the build or tests merely pass.

Before reporting completion:

1. render the changed screen in the actual app;
2. capture the same viewport/state as the approved reference when one exists;
3. compare hierarchy, spacing, typography, controls, alignment, wrapping and overflow;
4. exercise the primary interaction path;
5. exercise at least one error or partial-data path;
6. inspect a narrow and a wide desktop window;
7. inspect long labels, many rows/points and selected states;
8. check visible keyboard focus and tooltips for non-obvious icon-only actions;
9. verify that hidden, filtered, selected, QC-excluded and deleted data are visually distinguishable;
10. record remaining visual differences instead of calling the result finished.

If browser-rendered evidence cannot be produced, the result is `blocked for visual QA`, not `done`.

## PetroLab visual character

PetroLab is a professional scientific desktop application, not a marketing dashboard.

- Prefer a restrained green visual identity; do not drift toward the generic blue SaaS look.
- Keep useful scientific information dense but readable.
- Preserve clear hierarchy and breathing room around major work areas without wasting space.
- Do not make important data tiny for the sake of fitting more on screen.
- Use color semantically and never as the only carrier of meaning.
- Keep plot-series colors independent from UI state colors.
- One local primary action should visually dominate; secondary actions must not compete with it.
- Frequent actions should remain directly available instead of being hidden in overflow menus solely for visual minimalism.

## Scientific trust in UI

Never make these states look equivalent:

- measured vs calculated vs interpreted values;
- selection vs filter;
- hidden-on-plot vs QC-excluded;
- warning vs automatic correction;
- unsaved edit vs persisted value;
- deletion vs reversible visibility change.

Mass actions must show how many objects will be affected before execution.

## Implementation boundaries

Keep the existing architecture intact:

- React contains presentation and interaction, not scientific formulas, SQL or provenance rules;
- scientific calculations stay in Python core;
- Tauri remains the desktop shell and bridge;
- visual state must not silently mutate source analytical data.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites.

Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in the relevant product/design contract rather than relying on chat memory alone.
