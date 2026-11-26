// Thin shim: prints {"provider","model","tier"} as JSON for the cheapest model.
// Verified on a real run: resolveModel returns a bare model id string (no tier).
// The tier is then taken from the profile, which the Python guard also requires to be "economy".
import { resolveModel } from "llm-model-resolver";

const provider = process.argv[2];
const key = process.env.DISTILHEAD_PROVIDER_KEY;
if (!provider || !key) {
  console.error("usage: DISTILHEAD_PROVIDER_KEY=... node resolve_model.mjs <provider>");
  process.exit(2);
}
const r = await resolveModel(provider, key, { order: "cheapest" });
const model = typeof r === "string" ? r : r.id ?? r.model;
const profileTier = process.env.LLM_MODEL_RESOLVER_PROFILE === "economy" ? "economy" : "unknown";
const tier = (typeof r === "object" && r.tier) || profileTier;
console.log(JSON.stringify({ provider, model, tier }));
