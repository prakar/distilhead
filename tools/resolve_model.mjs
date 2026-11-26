// Thin shim: prints {"provider","model","tier"} as JSON for the cheapest model.
// UNTESTED against the real llm-model-resolver API; adjust the normalisation below.
import { resolveModel } from "llm-model-resolver";

const provider = process.argv[2];
const key = process.env.DISTILHEAD_PROVIDER_KEY;
if (!provider || !key) {
  console.error("usage: DISTILHEAD_PROVIDER_KEY=... node resolve_model.mjs <provider>");
  process.exit(2);
}
const r = await resolveModel(provider, key, { order: "cheapest" });
const model = typeof r === "string" ? r : r.id ?? r.model;
const tier = typeof r === "string" ? "unknown" : r.tier ?? "unknown";
console.log(JSON.stringify({ provider, model, tier }));
