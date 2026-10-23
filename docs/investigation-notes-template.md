# Private investigation notes: template

Copy this template to a working directory **outside the Git checkout**. The completed notes may contain response-bearing evidence and must not be committed. Use a separate record per challenge and a row per question. For public writing, use the [challenge guide template](../challenges/_template/how-to-solve.md).

## Task and constraints

- Challenge and objective: [description]
- Authorized scope: [supplied artifacts and permitted targets]
- Requested outputs and formats: [per-question requirements]
- Constraints and exclusions: [exact wording, including uncertainty in hints]
- Current status: [not started / investigating / candidate found / verified / blocked]

## Inputs and environment

- Originals: [private locations, sizes, file signatures, checksums]
- Working copies: [private locations]
- Tools and versions: [versions and relevant dependencies]
- Time conventions: [timezone, epoch, units, capture date]
- Missing capabilities: [unavailable tools, hardware, or artifacts]

## Evidence and confidence

| Question | Source location | Observation | Interpretation and assumptions | Verification performed | Status | Submission feedback |
| --- | --- | --- | --- | --- | --- | --- |
| [ID] | [file/packet/UID/offset/row] | [direct evidence] | [inference and alternatives] | [check and what it establishes] | [status] | [not submitted / accepted / rejected / unavailable] |

## Reproduction record

1. [Command or operation, input, tool version, and output location.]
2. [Transformation parameters, including encoding and normalization.]
3. [Verification against the original input and its limits.]

## Searches and failed approaches

| Hypothesis | Inputs or candidate set | Work completed | Observation | Reason to change approach |
| --- | --- | --- | --- | --- |
| [hypothesis] | [scope, rules, count] | [completed / interrupted; coverage] | [result without overclaiming] | [next useful distinction] |

## Active work and handoff

- Running jobs: [session/process, start time, purpose; or none]
- Checkpoints: [private paths and exact resume command]
- Uncertainties: [unverified assumptions or missing evidence]
- Next bounded experiment: [question to resolve, cost estimate, and success criterion]
- Pending user information: [only what is needed to proceed]
- Do not repeat: [completed searches and resolved issues]

## Public write-up review

- [ ] The guide describes what actually happened and distinguishes suggested alternatives.
- [ ] Final responses and response-bearing artifacts have been removed from the public version.
- [ ] Commands and links do not contain hidden responses or private working paths.
- [ ] Verification and remaining limitations are described without disclosing the result.
- [ ] Repository checks and manual staged-diff review have been completed.
