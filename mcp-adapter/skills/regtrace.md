# RegTrace

RegTrace is a policy-aware development workflow for Claude.

The user provides:

1. a local repository path,
2. a software feature or development request,
3. company policies, legal requirements, security policies, privacy rules,
   governance documents, or other requirements directly in the current
   Claude conversation.

Those user-supplied policy documents are the source of truth.

RegTrace does not invent missing laws, policies, obligations, or requirements.

---

## Mandatory workflow

For policy-aware development, always use this sequence.

### Phase 1 — Claude creates the initial plan

First understand the user's feature request and the existing project.

Create a concise implementation plan yourself.

Do not modify code yet.

### Phase 2 — RegTrace reviews the plan

Call `regtrace_review_plan`.

Provide:

- the local repository path,
- the feature intent,
- your proposed implementation plan.

Use both:

- the actual repository returned by RegTrace,
- all relevant company/legal policy documents supplied by the user in the
  current conversation.

Review the plan for policy-derived engineering problems.

Examples include, only when supported by the supplied policies:

- authorization and permission requirements,
- consent requirements,
- personal-data handling,
- data leaving the system,
- external integrations,
- encryption requirements,
- retention and deletion requirements,
- audit/logging requirements,
- access restrictions,
- approval workflows,
- security requirements,
- prohibited data collection,
- disclosure restrictions.

Do not merely repeat policy prose.

Determine what the policy means for this actual codebase and this actual plan.

If relevant repository files are missing from the returned snapshot, use the
repository tree and call `regtrace_review_plan` again with `focus_paths`.

Produce a revised implementation plan.

Only after this review should implementation begin.

---

## Phase 3 — Implementation

Implement according to the revised plan.

Preserve existing functionality unless the requested feature or policy
requirement requires a change.

Keep changes focused.

Do not alter company policy documents in order to make the implementation
appear acceptable.

When local source files must be changed through RegTrace, call
`regtrace_review_fix` with `action="apply"` and provide complete replacement
contents for the files being changed.

---

## Phase 4 — Mandatory post-implementation review

After implementation, always call:

`regtrace_review_fix` with `action="review"`.

This is a separate review.

Do not assume that following the approved plan means the resulting code is
correct.

Read the actual implementation.

Reason about real behavior.

Follow relevant execution paths across:

- functions,
- helpers,
- wrappers,
- modules,
- API clients,
- database operations,
- storage,
- authentication,
- authorization,
- validation,
- external network calls,
- data transformations,
- logging,
- queues and background jobs.

Do not rely only on function or variable names.

Compare the implementation directly with the policy documents supplied by the
user in the current conversation.

For each supported issue, identify:

- the relevant policy requirement,
- the affected file,
- the affected function or code path,
- the current software behavior,
- why that behavior conflicts with the supplied requirement,
- the smallest appropriate correction.

If more code is required to determine behavior, call the review tool again with
specific `focus_paths`.

Do not claim a violation when evidence is insufficient.

Do not invent a requirement that is absent from the supplied policies.

---

## Phase 5 — Fix

If the post-implementation review finds a real issue:

1. determine the smallest safe code correction,
2. call `regtrace_review_fix` with `action="apply"`,
3. apply complete replacement content for the affected files,
4. preserve unrelated behavior.

Do not stop after merely describing the fix.

---

## Phase 6 — Final review

After every fix, call:

`regtrace_review_fix` with `action="review"`

again.

Review the resulting code as a fresh implementation.

Continue only while there are concrete issues supported by the supplied
policies.

When no further supported conflict is found, clearly state that the reviewed
implementation is consistent with the supplied policy documents for the code
paths inspected.

Do not claim universal legal compliance.

The review is bounded by:

- the policies the user supplied,
- the repository content available,
- the code paths inspected.

---

## Security rules

Never expose or modify:

- `.env` files,
- private keys,
- certificates,
- credential files,
- secrets.

Never execute arbitrary repository code merely to inspect it.

Never weaken or rewrite a company policy to make code pass review.

Never invent policy requirements.

The supplied policy documents define the requirements.