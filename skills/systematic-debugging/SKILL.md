---
name: systematic-debugging
description: Debug failures with a reproduce → locate → hypothesize → fix → verify loop. Use when tests fail, runtime errors appear, behavior regresses, or the user says 排查/debug/为什么挂了/fix bug — not when writing greenfield features.
---

# Systematic Debugging

## Rules

1. **Reproduce first** — get a failing command, stacktrace, or minimal input. Do not “fix by vibe”.
2. **One hypothesis at a time** — state it in one sentence before changing code.
3. **Smallest fix** — prefer the local cause; do not rewrite surrounding systems unless the bug’s root is architectural.
4. **Verify** — re-run the same failing command; only then broaden tests if needed.
5. **Stop when verified** — do not keep “cleaning up” unrelated code in the same pass unless the user asked.

## Loop

```text
Reproduce → Read evidence → Hypothesize → Instrument/bisect → Patch → Re-run → Done
```

### 1. Reproduce

- Capture exact command, cwd, env flags, and full error.
- If flaky: note frequency; prefer a deterministic path (seed, single test, smaller input).

### 2. Locate

- Read the top frames of the stacktrace; open the first **project** frame (skip stdlib/site-packages unless necessary).
- Grep for the error message / return code / sentinel string.
- For “wrong behavior without crash”: compare expected vs actual at the nearest assertion or UI surface.

### 3. Hypothesize

Write (to the user, briefly):

> Suspect: X because Y. Next check: Z.

Bad: “maybe something with caching or async or the model…”
Good: “`LookupGuard` arm state is never reset after text-only turns, so the second tool batch skips the check.”

### 4. Fix

- Change the minimal code that falsifies the hypothesis.
- Prefer adding a regression test when the bug is logic (not env-only).

### 5. Verify

- Re-run the original failing command.
- If still failing: **new** hypothesis — do not layer more patches blindly.

## Anti-patterns

- Editing prompts / adding logs forever without a reproduction command
- Rewriting a module because “it feels messy” while chasing a one-line bug
- Declaring fixed without re-running the failure
- Asking the user for more context before reading the stacktrace and nearby code

## When to escalate

- External service / quota / SSL: report as environment, don’t invent app fixes
- Heisenbug after 2 solid hypotheses fail: add one targeted log or bisect commit, then continue
---

