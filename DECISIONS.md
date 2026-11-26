# Decisions

Not legal advice. Check YOUR provider's current terms before use.

## D1. Provider terms (records as of 2026-11-26; owner to verify links and re-check at build time)
- **Gemini API: allowed (default).** Terms (effective 2026-03-23) forbid using the Services "to develop models that compete with the Services"; no clause found against training on Output. Never enable grounding with Search/Maps. Link: TODO owner to add.
- **xAI: denied in code.** Enterprise ToS s3.2 forbids using Output "to train any foundation models, large language models, or other AI systems" unless an order form allows it. Link: TODO owner to add.
- **OpenAI: denied in code.** Bills over budget and has a competing-model clause. Link: TODO owner to add.
- Any other provider needs `<pack>/terms/<provider>.yaml` with `clause_url`, `date`, `summary`, and a line here.

## D2. Cost cap
Default and maximum pack cap is $5. Raising it needs the logged `Ledger.raise_cap(new, who, reason)` path; the tool never runs without a finite cap.

## D3. Scope
Python only in v1. Code licence MIT.
