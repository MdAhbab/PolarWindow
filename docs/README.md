# POLAR WINDOW Documentation

Index of project documentation, its scope, and intended audience.

| Document | Purpose | Target Audience |
|---|---|---|
| [README.md](../README.md) | What it is, three ways to try it, what to look at, how to test it, how to put it on a server, required datasets. | Newcomers, evaluators, operators |
| [system-design.md](system-design.md) | Architecture, module layering, domain models, algorithms, and performance budgets. | Backend engineers, systems architects |
| [api.md](api.md) | HTTP endpoint reference, uncertainty envelopes, error shapes, and rate limits. | Frontend engineers, API integrators |
| [lifecycle-api.md](lifecycle-api.md) | Contract and schemas for launch, trip, contact, and return lifecycle sections. | Frontend engineers, lifecycle developers |
| [validation.md](validation.md) | Physics validation against flown missions, ephemerides, and benchmark data. | Astrodynamicists, flight dynamics reviewers |
| [data-sources.md](data-sources.md) | Provenance, licenses, download URLs, and citations for all external datasets. | Data engineers, reviewers |
| [conventions.md](conventions.md) | Architecture invariants, numeric standards, coordinate frames, and wording rules. | All contributors |
| [runbook.md](runbook.md) | Single-host deployment (`docker compose`, `run_onVM.py`), configuration, troubleshooting, and pre-demo checks. | Operators, demo leads |
| [windows-setup.md](windows-setup.md) | Native Windows startup, project-local storage, prerequisites and data reuse. | Windows contributors |
| [planning-updates.md](planning-updates.md) | Wind verification scope, native rover terrain, pad-limit windows and pending external accounts. | Reviewers, operators |
| [test-plan.md](test-plan.md) | Test suites, test commands, pytest markers, and failure mode threat model. | Test engineers, developers |
| [adr/README.md](adr/README.md) | Index of Architecture Decision Records (ADR-0001 to ADR-0024). | Engineers, architects |
| [design-lifecycle.md](design-lifecycle.md) | Lifecycle view layout, interaction patterns, and frontend state specifications. | Frontend developers, UI designers |
| [design-visual-refresh.md](design-visual-refresh.md) | Visual refresh: audit of the current look, the direction, tokens, components, screens, motion, owner decisions and build slices. | Frontend developers, UI designers, the owner |
| [handoff.md](handoff.md) | How the product is put together, the rules that do not bend, how to run and check it, and where a review should look hardest. | Anyone picking the project up |
| [experience-plan.md](experience-plan.md) | The experience release: Ask, projects, scenarios, presets and the dashboard as a journey, with the wire contract. | Frontend and backend engineers |
| [design-audit-2026-11-12.md](design-audit-2026-11-12.md) | The November 2026 design audit: what was found on every route and where each finding is fixed. | Frontend developers, UI designers, the owner |
| [design-glossary.md](design-glossary.md) | The plain-words labels used on screen, with the technical term in brackets and the words that never appear. | Frontend developers, writers |
| [validation-2026-10-01.md](validation-2026-10-01.md) | Dated audit: which validations passed as science and which only ran. | Reviewers |
| [spenvis-manual-validation.md](spenvis-manual-validation.md) | How the radiation passages were compared with SPENVIS by hand, and the results. | Reviewers, radiation engineers |
| [copernicus-marine.md](copernicus-marine.md) | How to download and import the Copernicus Marine wave subset the Return section can read. | Operators |
| [openapi.json](openapi.json) | The generated API schema that `npm run codegen` turns into the frontend types. | Frontend engineers, API integrators |
