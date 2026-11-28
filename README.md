# distilhead

Keep a small text encoder frozen, train lightweight heads on it from an LLM teacher's labels, and run the result offline with no LLM. Domain content lives in packs; the core has none (a CI test enforces this). Not affiliated with Hugging Face or DistilBERT.

Step 0 status: scaffold, pack schema, toy pack, provider/model guard, cost ledger. No labelling, embedding or training yet.

## Quickstart

```
mise install
uv sync
uv run distilhead run packs/toy
```

Other commands: `uv run distilhead pack-validate packs/toy`, `uv run pytest`, `uv run ruff check .`.

Labelling later needs `node` (pinned in `mise.toml`) and `npm install` for the model-resolver helper, `LLM_MODEL_RESOLVER_PROFILE=economy`, and a key in `DISTILHEAD_PROVIDER_KEY` (env only, never committed).

## Provider terms

Using an LLM's output to train a model may be restricted by your provider's terms. Check yours. See `DECISIONS.md` for what this project decided and why.
