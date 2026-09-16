# Future production agents — intentionally deferred

MVP calculations and validation are deterministic Python. There are **zero mandatory
LLM endpoints** and no deployed specialist agents. Astral's development lanes do not
imply one production model per lane. A single explanation endpoint is optional and
separate from the framework migration; core dashboards must work without it.

Collect aggregate request category, duration, failures/timeouts, cache/fallback
outcomes and quantitative validation results without holdings or credentials. If an
LLM endpoint is approved later, record configured model/version, tokens, estimated
cost assumptions, retries and evaluation outcome. Use representative evaluations.

Before specialists or an orchestration framework, require an accepted ADR covering
baseline and sample coverage, objective quality thresholds, cost/latency budget,
measured benefit, maintenance burden, bounded retries/concurrency/escalation/spend,
rollout and rollback. Model self-confidence alone cannot trigger escalation.

Candidate routing is design only: deterministic code first; inexpensive capable
models only when ordinary code cannot satisfy a qualitative task; stronger models
only after demonstrated validation failure within budget. Verify actual API IDs and
prices at implementation time. Cache keys must include data/model/prompt versions,
parameters and user scope. Validate schema, sources and numbers in code.

A future packages/agents/README.md can link this design. No framework dependency,
service, supervisor loop, runtime router or paid API call is being introduced now.
