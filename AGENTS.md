# Working on Drawing

Read CONTRIBUTING.md before changing the project. Keep patches small enough to
review and bisect independently; every commit should build. Preserve authorship
when importing patches and link the original issue or pull request.

## Scope and style

Understand the failure before changing behavior. Explain the concrete trigger,
expected result, and cause. Avoid unrelated formatting or dependency changes.
Follow the surrounding Python style: tabs, roughly 80 columns, and existing
GTK/PyGObject patterns. Keep user-facing text translatable.

## Validation

Use the native Meson build and tests. Add a focused regression when it protects
an observable behavior or a difficult invariant. Keep exhaustive experiments,
benchmarks, temporary instrumentation, and investigation logs outside the source
unless maintaining them has a clear benefit. State exactly what was tested;
distinguish automated tests, isolated GUI checks, and physical-device testing.
Do not claim tablet, desktop, or packaging coverage that was not exercised.

For canvas and selection changes, check multiple tabs, zoom and scroll,
selection/import, edit/apply, deselection, and undo/redo as applicable. Preserve
alpha, image bounds, saved-state tracking, and history semantics.

## Submissions

Use a short component-prefixed title describing the change. A pull request
should explain the problem, the resulting behavior, and relevant validation.
Identify remaining limitations and dependencies. Keep commit-specific details in
commit messages. Do not turn submission prose into an investigation diary.

AI assistance is permitted under the human accountability policy in
CONTRIBUTING.md. An agent must not fabricate human review, approve a pull request without
explicit authorization, bypass protection, or merge work explicitly left for
human review. Repository rules apply to the maintainer too.
