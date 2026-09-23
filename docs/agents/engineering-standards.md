# Engineering standards

Use this baseline during implementation and review.

## Baseline

- **Follow the surroundings.** Follow project conventions and explain necessary departures.
- **Complete the task.** Deliver the requested behaviour and relevant failure paths.
- **Replace outright.** A change leaves one way to do the thing. Callers and tests move with that way.
- **Test behaviour.** Derive assertions from requirements, contracts, or defects. For fixes, show the regression fails on the bug where practical. Name tests by scenario and expected result.
- **Automate deterministic rules.** Use lint, types, and tests. Keep their configuration in tools, not in this file.

## Project constraints

- **Applications.** Do not write a separate resume per JD. Roles stay on domestic Agent / LLM application work, including LLM-application roles that write code. The city is Hangzhou; add a role only when the JD states that remote work is allowed. Do not change the project bullets in the PDF.
- **Boundary.** The screening runtime lives at the repo root in `src/boss_screen/`. The workbench only changes `screen/`, and reads the repo-root `boss.yaml` itself. This repo maintains application materials and application progress. It is not a hiring platform and not a business backend.
- **Personal tool.** Do not publish. Prefer one less choice, mode, or field. The owner being able to read and change it beats foolproofing and automatic tracking.
- **Evidence.** Experience and numbers come from the `resume/` JSON. Use oral notes only when the owner points at them in the current turn. Open-ended answers use only text already in the application body.

## Smells

Review cues from Fowler, _Refactoring_, ch. 3. Tie findings to concrete impact and choose a proportionate remedy.

- **Mysterious Name:** clarify the name or the responsibility it struggles to express.
- **Duplicated Code:** extract shared knowledge that must change together.
- **Feature Envy:** move behaviour toward the data and responsibility it belongs to.
- **Data Clumps:** group values that form one concept or invariant.
- **Primitive Obsession:** use a domain type to express meaning or exclude invalid states.
- **Repeated Switches:** centralize recurring dispatch that changes together.
- **Shotgun Surgery:** gather responsibility when one rule requires scattered edits.
- **Divergent Change:** separate a module's independent reasons to change.
- **Speculative Generality:** remove abstractions and hooks without a current use.
- **Message Chains:** hide traversal that exposes implementation details.
- **Middle Man:** remove delegation that adds no policy or useful boundary.
- **Refused Bequest:** repair an unfulfilled interface contract or prefer composition.
