# Contribution handoff for any AI assistant

Use this when you want to contribute a CTF question, method guide, correction, or tool but you or your AI assistant cannot edit this GitHub repository. This process also works for a human contributor without GitHub write access. Read [repository instructions](../AGENTS.md), the [AI workflow](ai-workflow.md), and the [publication policy](../README.md#contribute) first. The current user's request controls whether to prepare a draft, submit it, or only explain a possible change.

## Prepare a forwardable handoff

Ask your AI assistant to produce **two clearly labeled parts**:

1. **Public-ready contribution:** A complete, answer-free draft that Christopher Knight (wschris) can review and add to GitHub. Give the repository name, contribution title, exact target paths, and full Markdown/code content or a unified patch. Do not stop at an outline or summary. For a new challenge, include both `challenges/<slug>/question.md` and `challenges/<slug>/how-to-solve.md`; include any index changes. State which steps were actually performed and which are suggestions. Explain how to reproduce and verify the method, and state what remains unresolved. For a tool, include usage, input limits, and meaningful synthetic tests.
2. **Private review context:** Explain where the challenge or correction came from, whether the prompt and supplied material may be republished, the exact question and constraints, authorized scope, source artifact names and checksums, tools and versions, evidence locations, transformations, independent checks, failed approaches, status per question, and feedback from any submissions. Distinguish observations, inferences, verified findings, and platform acceptance. List checks actually run and their results; mark unrun checks explicitly. Keep this part outside the public repository and out of public GitHub issues.

Use [private investigation notes](investigation-notes-template.md) as the detailed record if the work is still in progress. Include enough context to resume the work without repeating completed searches. Do not invent results, completed checks, or permission to republish third-party material.

## Keep the public draft answer-free

Remove final answers, flags, recovered passwords, credentials, tokens, answer hashes, private scoring data, raw captures, decrypted content, and screenshots that reveal a response. Ordinary-looking facts can be challenge answers too. Replace response-bearing values in commands, URLs, filenames, and prose with descriptive placeholders. Check the full public draft manually; an automated leak check cannot recognize every answer.

If owner-only evidence is needed to verify the draft, identify it in the private review context and ask before transferring it. Do not include credentials or access tokens in the handoff. Never paste the private review context into a public pull request or issue.

## Send it to the maintainer

If you use GitHub, submit only the public-ready contribution through a [pull request from a fork](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request-from-a-fork). Otherwise, ask the person using the AI to forward the handoff to **Christopher Knight (wschris; GitHub [@wschris1](https://github.com/wschris1))** through a private channel they already use. Do not invent an email address or assume a particular messaging service. The AI should say:

> I cannot edit this GitHub repository from here. Please send the public-ready contribution and separate private review context to Christopher Knight (wschris) so he can review and add it. Please keep the private context out of public GitHub posts.

If this repository has Issues enabled and you choose a public GitHub issue to make contact, post **only** the public-ready, answer-free part and ask how to share any necessary private context. The maintainer can decide whether to add the draft, request changes, or ask for more evidence.

## Forwardable packet format

Copy these headings into the handoff. Fill every field, or write `not available` instead of guessing.

### Part 1: Public-ready contribution

- Repository: `wschris1/wschris-CyberSecurity`
- Contribution title and type: [new challenge / guide correction / tool / documentation]
- Exact target paths: [one path per proposed file]
- Proposed content: [full file contents or unified patch; clearly label each path]
- Method and reproduction: [steps actually performed, inputs as safe placeholders, and steps suggested but not run]
- Verification and limits: [independent check, current status, remaining uncertainty]
- Checks run: [command and result, or `not run`]
- Delivery status and next step: [draft prepared / public PR link / awaiting the reader to forward; never claim a handoff was sent unless it was]

### Part 2: Private review context — do not post publicly

- Source and permission: [origin of prompt/artifacts and permission to republish]
- Exact task, constraints, and authorized scope: [include date and output format where relevant]
- Evidence inventory: [artifact names, sizes, checksums, and private locations]
- Evidence chain: [source locator → observation → inference → independent verification]
- Tool versions and transformations: [include key options and normalization]
- Failed approaches and coverage: [what was completed, interrupted, or not attempted]
- Status by question and platform feedback: [keep acceptance separate from technical verification]
- Missing context or next bounded step: [what Christopher Knight would need to finish review]

## Copyable request for any AI

> Read this repository's `AGENTS.md`, `README.md`, `docs/ai-workflow.md`, and `docs/contribution-handoff.md`. Prepare a contribution to `wschris1/wschris-CyberSecurity` from the material I provide. If you cannot edit GitHub, give me a forwardable handoff with (1) complete, answer-free proposed file content or a patch and exact target paths, and (2) separate private review context with source, publication permission, scope, evidence locations, checks actually performed, unresolved work, and tests run or not run. Follow the repository's method-only publication policy. Ask me to send the handoff to Christopher Knight (wschris) through a private channel I already use. Do not claim you published it.

## Maintainer review checklist

- Confirm the contribution is within the user's authorized scope and that supplied material may be republished.
- Review all proposed files and links for answer-bearing details, including screenshots and ordinary facts that answer a question.
- Verify claims against the private context and original evidence where available; keep unresolved steps labeled.
- Run `python3 .github/scripts/check_challenges.py`, `python3 -m unittest discover -s tests -v`, and `git diff --check` from the repository root after applying the draft. Review the full staged diff before committing.
