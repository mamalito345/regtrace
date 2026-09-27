# RegTrace

### Policy-aware development for Claude

**Built for the IBM Bob 2.0 Hackathon and LexHack 2026.**

RegTrace brings company policies, privacy requirements, security rules, and other organization-specific constraints directly into the AI-assisted software development workflow.

Instead of checking policy only after software has already been built, RegTrace introduces review at two critical points:

**before implementation** and **after implementation**.

The workflow is simple:

```text
Company Policies
      +
Local Repository
      +
Feature Request
      ↓
Claude creates a plan
      ↓
RegTrace reviews the plan
      ↓
Claude revises the plan
      ↓
Claude implements
      ↓
RegTrace reviews the actual code
      ↓
Claude fixes supported policy conflicts
      ↓
RegTrace performs a fresh review
```

RegTrace runs as a local MCP extension for Claude Desktop.

Claude remains the reasoning and coding agent.

RegTrace supplies the repository context, the policy-review workflow, and controlled local file modification tools.

---

# The Problem

Modern coding agents can understand large software repositories.

But they do not automatically understand the rules that the organization expects that software to follow.

Those requirements are often stored separately in:

- privacy policies
- security policies
- legal requirements
- governance documents
- data-handling rules
- approval procedures
- internal engineering policies
- regulatory guidance

This creates a gap between:

```text
What the developer wants to build
```

and:

```text
What the organization allows the software to do
```

A feature may work perfectly from a technical perspective while still conflicting with an internal policy.

RegTrace is designed to close that gap.

---

# How RegTrace Works

The developer provides Claude with three things:

```text
1. A local repository path
2. A feature request
3. Relevant company or legal policy documents
```

The policy documents are attached directly to the same Claude conversation.

The repository remains local and is accessed through the RegTrace MCP extension.

---

## Phase 1 — Initial Plan

Claude first creates its own implementation plan.

Example:

```text
Feature:
Export customer information to an external CRM.
```

Claude might initially propose:

```text
1. Read the customer record.
2. Serialize customer information.
3. Send it to the CRM API.
4. Log the export event.
```

No code is modified yet.

---

## Phase 2 — Plan Review

Claude calls:

```text
regtrace_review_plan
```

RegTrace provides Claude with:

- the real repository structure
- relevant source files
- the RegTrace review skill

Claude then compares the proposed plan with the policy documents supplied in the conversation.

For example, a company policy might state:

```text
Customer personal data may only be exported to an external service
after explicit user consent.
```

Claude can now identify that the initial implementation plan is missing a consent gate.

The plan is revised before implementation begins.

---

## Phase 3 — Implementation

Claude implements the revised plan.

The implementation is performed against the actual local repository.

RegTrace does not use a second LLM.

Claude itself remains responsible for understanding and modifying the software.

---

## Phase 4 — Post-Implementation Review

After implementation Claude calls:

```text
regtrace_review_fix
```

with:

```text
action="review"
```

RegTrace returns the actual resulting source code.

Claude performs a fresh review against the supplied policies.

The review can follow behavior across:

- functions
- helpers
- wrappers
- modules
- API clients
- database operations
- authentication
- authorization
- external network calls
- data transformations
- storage
- logging
- background jobs

The goal is to inspect the real behavior of the resulting implementation rather than relying only on names or the original plan.

---

# Example

Consider this implementation:

```python
def export_customer(customer):
    if customer.export_consent:
        audit.log("consent-observed")

    crm.send(customer.email)
```

And the supplied company policy:

```text
Customer personal data may only be exported to an external service
after explicit user consent.
```

The software runs correctly.

But the policy condition is not actually protecting the external transfer.

The CRM call executes regardless of consent.

RegTrace allows Claude to identify the real code path:

```text
customer_export.py
        ↓
export_customer()
        ↓
consent condition only controls logging
        ↓
crm.send() still executes
```

Claude can then correct the implementation:

```python
def export_customer(customer):
    if not customer.export_consent:
        raise PermissionError(
            "Explicit export consent is required."
        )

    crm.send(customer.email)
```

After the correction, RegTrace requires another fresh review.

---

# The Development Loop

```text
┌─────────────────────────────┐
│        Feature Request      │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│      Claude Creates Plan    │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│    RegTrace Plan Review     │
│                             │
│ repository + policies       │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│      Revised Plan           │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│      Claude Implements      │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│    RegTrace Code Review     │
└──────────────┬──────────────┘
               ↓
          Issue found?
          /          \
        yes          no
         ↓            ↓
  Claude fixes      Finish
         ↓
   Review again
```

---

# Architecture

The default RegTrace workflow is intentionally small.

```text
Claude Desktop
      ↓
RegTrace MCP Extension
      ↓
┌─────────────────────────────┐
│ regtrace_review_plan        │
│ regtrace_review_fix         │
└─────────────────────────────┘
      ↓
Local Repository
```

Policy documents remain in the Claude conversation:

```text
Claude Conversation
├── Feature Request
├── Company Policy
├── Privacy Policy
├── Security Policy
└── Other Requirements
```

The intelligence remains in Claude.

RegTrace shapes the development workflow around the organization's supplied requirements.

---

# MCP Tools

RegTrace exposes two primary tools.

## `regtrace_review_plan`

Used before implementation.

It provides Claude with the real repository and the RegTrace review instructions so Claude can review its proposed implementation plan against the supplied policies.

Conceptually:

```text
Initial Plan
     +
Repository
     +
Policies
     ↓
Policy-aware revised plan
```

---

## `regtrace_review_fix`

Used after implementation.

It supports two actions.

### Review

```text
action="review"
```

Claude receives the resulting repository source code and performs a new policy review.

### Apply

```text
action="apply"
```

Claude can write complete corrected file contents back to the local repository.

After every apply operation, another review is required.

```text
Review
   ↓
Issue
   ↓
Apply Fix
   ↓
Fresh Review
```

---

# Repository Structure

```text
regtrace/
│
├── README.md
├── .gitignore
├── index.html
│
├── website/
│   └── index.html
│
├── mcp-adapter/
│   ├── manifest.json
│   ├── requirements.txt
│   ├── server.py
│   │
│   └── skills/
│       └── regtrace.md
│
├── regtrace-core/
│
├── tests/
│
└── examples/
    └── demo_app/
```

### `mcp-adapter`

The primary working RegTrace implementation used by Claude Desktop.

### `regtrace-core`

Experimental and earlier RegTrace analysis infrastructure.

It is preserved in the repository for development and research purposes, but it is **not required for the default Claude Desktop workflow**.

### `tests`

Automated tests for the RegTrace codebase.

Current local test result:

```text
99 passed
```

### `examples`

Contains small demonstration projects for testing the RegTrace workflow.

### `website`

Static one-page project website used to present RegTrace.

---

# Installation

## Requirements

You need:

```text
Windows
Python 3.10+
Claude Desktop
Git
```

RegTrace currently uses the Python MCP SDK.

---

## 1. Clone RegTrace

Open PowerShell:

```powershell
git clone https://github.com/mamalito345/regtrace.git
cd regtrace
```

---

## 2. Install Dependencies

Run:

```powershell
python -m pip install -r .\mcp-adapter\requirements.txt
```

The primary dependencies are:

```text
mcp[cli]>=2.2,<3
pydantic>=2.12,<3
```

---

## 3. Test the MCP Server

Run:

```powershell
cd .\mcp-adapter
python -c "import server; print('REGTRACE MCP OK')"
```

Expected output:

```text
REGTRACE MCP OK
```

Return to the repository root:

```powershell
cd ..
```

---

# Installing RegTrace in Claude Desktop

Open:

```text
Claude Desktop
```

Then navigate to:

```text
Settings
    ↓
Extensions
    ↓
Advanced settings
    ↓
Extension Developer
    ↓
Install unpacked extension
```

Select:

```text
regtrace\mcp-adapter
```

Restart Claude Desktop.

RegTrace should now expose:

```text
regtrace_review_plan
regtrace_review_fix
```

to Claude.

---

# Using RegTrace

Open a new Claude Desktop conversation.

Attach the relevant policy documents.

For example:

```text
privacy-policy.pdf
security-policy.md
company-ai-policy.pdf
```

Then give Claude your repository path.

Example:

```text
C:\Projects\customer-app
```

And describe the feature you want to build.

---

# Starter Prompt

```text
Use RegTrace for this development task.

Repository:
C:\PATH\TO\MY\PROJECT

Feature:
[Describe what you want to build]

I have attached the relevant company/legal policy documents
to this conversation.

Follow the full RegTrace workflow.

1. First create your own implementation plan.

2. Before writing code, call regtrace_review_plan and review
   your plan against the actual repository and the attached
   policy documents.

3. Revise the implementation plan based on that review.

4. Implement the revised plan.

5. After implementation, call regtrace_review_fix with
   action="review".

6. Review the actual resulting source code against the
   attached policies.

7. If you find a concrete conflict supported by the supplied
   policy, correct it using regtrace_review_fix with
   action="apply".

8. After every correction, call action="review" again and
   perform a fresh review.

Do not invent policy requirements.

Do not modify the policy documents.

Do not stop after merely describing a required code fix.
```

---

# Running the Tests

From the repository root:

```powershell
python -m pytest tests -q
```

Current verified local result:

```text
99 passed
```

---

# Demo Project

A small demonstration repository is available under:

```text
examples/demo_app
```

The example can be used to demonstrate a customer-data export policy.

Typical demo flow:

```text
Attach policy
     ↓
Give Claude demo repository path
     ↓
Ask Claude to implement customer export
     ↓
RegTrace reviews the plan
     ↓
Claude implements
     ↓
RegTrace reviews actual code
     ↓
Policy issue detected
     ↓
Claude fixes code
     ↓
Fresh review
```

This provides a small reproducible example of the full RegTrace workflow.

---

# Security Boundaries

RegTrace includes several safeguards for local repository access.

It ignores common directories such as:

```text
.git
.venv
venv
env
node_modules
dist
build
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
```

It also refuses to work with common secret files including:

```text
.env
.env.local
.env.production
credentials.json

*.pem
*.key
*.p12
*.pfx
```

Repository writes are restricted to paths inside the selected repository.

Path traversal outside the repository is rejected.

RegTrace does not execute arbitrary repository code simply to inspect it.

---

# Policy Boundaries

RegTrace does **not** attempt to invent laws or requirements.

The policy source of truth is the material supplied by the user.

A review is bounded by:

```text
the supplied policy documents
+
the repository content available to Claude
+
the code paths actually inspected
```

Therefore RegTrace should not be interpreted as providing universal legal compliance certification or legal advice.

Its purpose is:

> **policy-aware software engineering review against supplied requirements.**

---

# Why MCP?

RegTrace uses the Model Context Protocol because the coding agent needs access to real local development context.

The MCP extension allows Claude to work with:

```text
Real repository
        +
Real feature request
        +
Real organization policies
```

without creating a separate AI application.

Claude remains the interface.

RegTrace becomes part of the coding workflow.

---

# Website

The project website is included in:

```text
website/index.html
```

It can be opened directly in a browser.

Or run locally:

```powershell
cd website
python -m http.server 8080
```

Then open:

```text
http://localhost:8080
```

---

# Project Website and Source

GitHub:

https://github.com/mamalito345/regtrace

---

# Hackathons

RegTrace was developed as a hackathon project for:

### IBM Bob 2.0 Hackathon

and

### LexHack 2026

The project explores a simple question:

> What if company policies were not documentation developers checked later, but active context used by the coding agent while software was being planned and built?

RegTrace is our implementation of that idea.

---

# Current Status

The current local implementation has been validated with:

```text
RegTrace MCP import: PASS
Automated tests:     99 passed
Claude Desktop MCP:  connected
Plan review:         working
Code review:         working
Local code fixes:    supported
```

---

# RegTrace

**Your code already has an AI agent.**

**RegTrace gives that agent the rules it needs to build with.**