# Phase 4a — Hermes’ Dispatch: local human handoff

## Delivered

Saved Oracle turns can explicitly create local support tickets. Dispatch shows the question, escalation reason, saved response/evidence, current citation labels, original conversation link when available, internal notes, status, and ordered activity. No email, notification, or customer message is sent. Ticket operations do not call Gemini or Ollama.

The Oracle’s uncertain/unsupported output already suggests human review; this milestone connects that suggestion to an actual local record. Broader Phase 3 question-coverage, scope, and adversarial review remain open. Reviewed evaluation and handoff precision/recall remain Phase 5, not inferred from successful ticket creation.

## Creation and workflow

In The Oracle, open a saved answer and choose **Create local support ticket**, then **Open local support ticket**. Ticket creation is never automatic. A missing/invalidly cited answer uses its stored reason code; an accepted answer can also be manually escalated with `requested_review`. A clarification turn uses `clarification_review`.

The API takes only conversation/turn IDs and resolves the saved turn server-side. It does not accept a forged question, reason, model-supplied action, or browser-supplied evidence snapshot. One ticket is allowed per saved turn; duplicate/concurrent creates return the existing ticket without adding duplicate activity. An unknown or mismatched origin is rejected.

Statuses are `open`, `in_progress`, and `resolved`. A status change or note is saved transactionally with a new revision/activity entry. Resolving requires a nonblank resolution note. Reopening clears the current resolution field, while earlier resolution notes remain in activity. A note can be added without changing status. Empty/no-change updates are rejected. A manually resolved ticket is a workflow state, not proof that an answer is correct or that a customer was contacted.

Updates and deletion require the last observed revision. A competing tab’s edit returns 409 instead of overwriting changes. Refresh the ticket and review its current state before retrying. Browser async mutations are fenced to the selected ticket, so navigating to another ticket does not replace its detail with a late response.

## Persistence and retention

Tickets use a dedicated, ignored `data/local/alethia-tickets.sqlite3` (schema 1), leaving document schema 3, conversation schema 1, and encoder artifacts unchanged. Inserts, updates, and deletion use `BEGIN IMMEDIATE`; activity writes share the same transaction. A failed activity insert rolls back the ticket/status change. Event rows cascade when the ticket is deleted.

- At most 500 tickets.
- At most 50 activity events per ticket, including creation.
- A saved origin snapshot is limited to 32 KiB.
- Internal notes/resolution notes are limited to 2,000 characters.
- IDs are opaque UUIDs; displayed short references are convenience labels.

Ticket snapshots retain question, accepted claims/quotes, source references, generation status/reason, model version, prompt version, and corpus identity. An abstained turn has no accepted answer/evidence even if retrieval found candidates; Dispatch does not invent a rejected-context explanation or claim access to live inventory.

Deleting a conversation does not delete a ticket. Its separate snapshot remains, and the origin link is disabled if that conversation/turn no longer exists. Document changes/deletion similarly preserve historical ticket quotes while marking their citation state as changed/deleted. Current-source links are shown only after exact revision/offset/text checks. Users must delete the ticket separately to remove its logical copy. SQLite deletion is not secure erasure.

This is a single-user local application, not a multi-tenant support service. Activity is an application history, not a tamper-proof audit log or authenticated staff identity. Assignment, customer contact details, email delivery, notifications, automatic routing, and external helpdesk integrations are outside this milestone.

## API and UI

- `POST /api/tickets`: `{conversation_id, turn_id}` → 201 `created` or 200 `existing`, plus the ticket detail.
- `GET /api/tickets?status=open|in_progress|resolved`: status-filtered summaries; omit status for all.
- `GET /api/tickets/{id}`: snapshot, fresh citation states, origin availability, ordered events.
- `PATCH /api/tickets/{id}`: `{expected_revision, status, note}`.
- `DELETE /api/tickets/{id}?expected_revision=N`: explicit revision-protected removal.
- Saved-conversation reads add each turn’s current `ticket_id`; it is not embedded permanently into the original answer snapshot.

The UI supports bookmarkable `#dispatch?ticket=<id>` links, status filters, refresh, origin navigation, evidence inspection, notes, resolving/reopening, and deletion confirmation/cancellation. Dates display in Africa/Cairo time. Model/answer provenance remains associated with the original turn; tickets do not imply new Gemini output.

## Acceptance checks and observed result

All 193 backend tests pass, with one existing Starlette/AnyIO deprecation warning; `pip check` and strict TypeScript/Vite production build pass. Tests cover explicit creation, idempotence, concurrent duplicate requests, status filters, restart persistence, ordered Arabic notes, required resolution notes, reopening, compare-and-swap conflicts, wrong-origin rejection, source changes/deletion, conversation deletion with retained snapshot, capacity, transaction rollback, deletion cascade, and API schema validation. Ticket API tests prohibit model execution.

A real browser handoff used the previously saved fictional Gemini live-stock question. It created ticket `a2b516457f494fb9a37a6616d81090cb` in Open state, then moved it to In progress with a note that human inventory review is still needed and no customer message has been sent. It remains available as a meaningful demo ticket rather than being falsely marked resolved.

Local API checks confirmed duplicate creation returns the same ticket, an old-revision update returns 409 without adding activity, and status filters match the record. An actual API process restart retained the full ticket, its two events, and its conversation link. Five existing saved conversations were preserved. The original six demo documents and 28 source identities/content matched the pre-milestone SHA256 digest; no reindexing, model download, dependency installation, or new Gemini request was required.

The functional report is ignored under `reports/generated/phase4a-live-checks.json`. It records workflow observations only, not a model-quality or handoff-precision benchmark.

Browser checks verified the existing-ticket link after returning to the conversation, Open-only filtering, required resolution-note gating, and deletion-confirmation cancellation. Mobile 390×844 and desktop 1440×1050 layouts showed no horizontal page overflow. The final browser error-log check was empty, and a Dispatch preview was saved outside the repository. API/frontend remain running with the demo ticket open in the browser. No commit or push was made.

## Remaining work

Prepare Themis’ reproducible evaluation data format, review workflow, and transparent metric implementation. Separate unreviewed development cases from a frozen held-out set; report only actual experiment results. Continue generation coverage/scope/adversarial review alongside that evaluation work. No benchmark scores or calibrated handoff quality are claimed here.
