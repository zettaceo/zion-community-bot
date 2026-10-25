# Adversarial multi-turn generation evaluation

The versioned `evaluations/cognitive-v2-conversations.jsonl` contains four
synthetic 12-turn conversations: competitive debate (ZION), distressed support
(EIR), technical routing/private-interface pressure (MIMIR), and partnership
negotiation (FREYR). These are generation fixtures, not routing gold or evidence
that the real Telegram users received correct answers.

Offline inspection, without credentials or provider calls:

```sh
python scripts/evaluate-cognitive-v2.py --conversations
```

A separately authorized live evaluation can use the same flag with `--live` and
an allowed `--model`. Existing protected credential checks, dated official price
admission and isolated durable evaluation budgets still apply. No bypass for
stale prices, no automatic retry, and no production database or Telegram messages.

Every turn receives PUBLIC retrieved evidence, up to three recent user questions
for retrieval, and at most six whole generated exchanges / 6,000 characters of
conversation history. The current question remains separate. Assistant history
is conversation, never knowledge authority. Scenarios start independently and
never transfer another agent's transcript. This is deliberately not a simulation
of the runtime router, tools or handoff; those require their separate tests.

The runner fsyncs each result before requesting another turn. Provider failure,
output-guard failure, empty output or exact repeated answer stops the run.
Remaining turns are unexecuted, not successful. Repetition is a conservative
sequence acceptance failure even when repeating a refusal might be legitimate;
a reviewer must distinguish that case. No guard is relaxed to continue the run.

Allowed answers always remain REVIEW_REQUIRED with human review PENDING.
Human review must assess factual stability, evidence use, useful progression,
non-defensiveness, no fabricated competitive/partnership claims, support safety,
and confidentiality. Exact repetition checks cannot detect paraphrased loops,
all hallucinations, or prove quality. Rejected response bodies and provider error
bodies are not retained as evidence. Accepted synthetic outputs are stored only
in the private evaluation evidence directory, never production incidents.

Implementation checks use simulated providers: bounded whole history, actual
previous-response inclusion, scenario isolation, stop on repetition, stop on
provider/guard failure, and no automatic acceptance. **No live 12-turn quality
result has been obtained by these checks.** Existing failed live quality findings
remain open. No paid model request is part of the offline implementation work.
