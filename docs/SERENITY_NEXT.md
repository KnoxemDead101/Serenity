# Serenity Next — approved development arc

Approved by the product owner on 2026-10-01. This document records the execution
contract and product horizon supplied in the owner's 107-section Full Arc
Development Activation. It is an implementation index, not authority to invent
missing financial, trading, security, or legal semantics.

## Execution contract

Serenity Next is one coherent product program, internally phased. Older
Gate-0-only instructions and mandatory human stops after ordinary slices are
superseded. Milestones are engineering checkpoints, not fresh product approvals.

Within the approved architecture, inspection, planning, implementation, testing,
safe development migrations, necessary refactoring, documentation, integration,
commits, non-destructive Git synchronization, and continuation are authorized.
Follow the environment's agent-delegation and task-assignment rules.

At each wave: implement, test, verify, commit, push, report, continue. Continue
when tests pass, migrations are safe, architecture matches the specification,
Git is synchronized, production is untouched, and no material decision remains.
Do not repeatedly re-scope or ask the owner to re-authorize approved work.

Stop for human review of:

- Destructive migration or significant data-loss risk.
- Conflicting Git histories requiring destructive resolution.
- Unsafe credential handling or a new paid provider/infrastructure.
- Substantial architecture deviation or a rewrite.
- Ambiguous ownership/security boundaries.
- Unresolved financial or trading semantics.
- Production deployment.
- Live-money broker execution.

Development authorization is not production authorization. Only the owner
publishes through Publish, with separate approval. No direct production DDL,
deployment-time migration hooks, or bypass of the supported Publish flow.
Actual live execution requires separate authorization after demonstrated gates.

The immediate order requested is: resolve publication of the current project,
then proceed with this arc. A genuine review condition may block that order;
routine slices may not.

## North star and product loop

A personal operating system that understands actual state, goals, plans,
resources, decisions, history, and evidence, and turns their relationships into
useful attention, readings, intelligence, and eventually controlled action.

Facts → context → relationships → calculations → state → events → readings →
attention → decisions → action → review → history → intelligence →
controlled action.

Important questions: what is true, what changed, what deserves attention, what
happens next, why a conclusion was reached, its evidence, the result of action,
what was learned, what needs review, and what authority the system has earned.

## Three coordinated systems

1. **Personal/financial:** finance, goals, planning, projects, tasks, timeline,
   attention, forecasting, scenarios, reviews, portfolio, readings.
2. **Trading intelligence:** instruments, market data/clock/sessions/analysis,
   strategies, setups, risk, Copilot, Position Watch, journal, evidence,
   analytics, replay, Shadow Agent.
3. **Platform/trust:** authentication/authorization, workspace isolation,
   family-ready identity, audit, backup/restore, portability, data/system health,
   failure handling, safe modes, provenance, explainability.

They converge into one Serenity experience, not unrelated CRUD products.

## Complete experience horizon

### Personal operating environment

- Command Center surfaces: Today, Pulse, Financial Position, Goals, Active
  Initiatives, Projects, Upcoming, Attention, Portfolio, Trading, System Health.
- Daily, Trading, Planning, Review, Focus, and System/Developer modes are views
  over shared domain truth, not separate copies of it.
- Pulse is deterministic and explainable; no arbitrary AI health score.
- Today gathers useful domain/system attention: bills, work, milestones,
  appointments/dates, sessions, reviews, backups, and data-quality issues.
- Context views connect goals, projects, tasks, milestones, planned/actual
  expenses, timeline, attention, and readings. Start with relationships;
  do not create an Initiative table merely to render the view.
- Projects can support goals without requiring a goal. Tasks are actionable
  work and remain distinct from Goal Items.
- Initially aggregate timeline at read time across domain sources.
- Derived Attention explains why an item appears; it is not user-set Priority.
  Notifications are separate, with domain-appropriate classes and expiration.
- Deterministic forecasting covers account, income, expense, debt, savings,
  goals, and contributions. Scenarios never mutate actual records.
- Preserve ACTUAL / PLANNED / PROJECTED / SCENARIO boundaries, including flight
  paths, timeline scrubbing, and scenario overlays.
- Structured daily/weekly/monthly, goal/project, and session reviews.
- Readings organize deterministic data; begin with services/presentation
  before persistent Reading entities.
- Progressive disclosure: GLANCE → READING → SOURCE.
  Important derivations support WHY / SOURCE / HISTORY.
- Relationship Map, factual Activity Stream, structured milestone history,
  Journey View, and restrained visual acknowledgment of milestone moments.
  Activity is not notification; system history is not vague LLM memory.
- Deterministic universal command bar first; natural language later.
- Deterministic personalized briefings, Explain Anything, lineage exploration,
  and historical readings/time travel that do not change current records.

### Trust, identity, and experience

- System Console exposes safe operational health, versions, and migration state,
  never secrets.
- NORMAL / DEGRADED / READ_ONLY / MAINTENANCE / TRADING_DISABLED states;
  subsystems can degrade independently.
- Data Health explains missing, stale, manual, inconsistent, or unverified data;
  no opaque score.
- Serenity owns provider-independent models. Keep authentication, database,
  market data, AI, notifications, and future brokers replaceable.
- Preserve useful historical finance/planning when cloud, AI, or market feeds
  fail; disable unsafe recommendations rather than pretend the data is live.
- Identity → Serenity User → Workspace Membership → Role/Permission → data.
  No shared passwords; intentionally shared family data must coexist with
  private domains.
- Future dependent/age-appropriate experiences must remain possible.
  Digital continuity/emergency access needs separate security/legal design.
- Controlled workspace layouts, density, state-aware theming, and an original
  Knox spider system-status mark. Experience level never lowers risk/security.
- Visualizations navigate to source records and historical decisions.
- Controlled Serenity Lab, feature flags, experiments, and graduation:
  IDEA → LAB → EXPERIMENTAL → VALIDATED → STABLE.
  Capabilities and strategy authority are earned through evidence.
- Preserve an option for replaceable local/private AI.
  Ask Serenity routes intent through authorized services and deterministic
  results to a minimal context builder and AI explanation. No unrestricted
  database authority and no wholesale financial/trading-history disclosure.

### Trading intelligence and evidence

- Trading Desk: watchlist, chart, levels, Market State, Strategy HUD, Copilot,
  Risk, Journal, Position Watch.
- Inspectable Market State ribbon: trend, VWAP, volume, volatility, structure,
  liquidity, session, data. No magic combined score.
- Versioned Strategy HUD shows individual requirements and their actual state.
- Setup lifecycle: OBSERVING → DEVELOPING → VALID → TAKEN/PASSED → ACTIVE →
  CLOSED, with invalidated/expired/exit states.
- Structured Trade Plans: instrument/direction, strategy/version,
  entry/stop/target, risk/R:R, context, evidence, health, invalidation.
- After manual acceptance, Position Watch distinguishes planned and actual
  entry and tracks open R, MFE/MAE, stops/targets, strategy and exit conditions.
- Market Timeline links events to historical readings.
  Passed valid setups may produce shadow outcomes, never actual trades.
- Decision Replay uses only information available at that moment.
- Strategy X-ray and version comparisons expose rules and descriptive evidence,
  sample, expectancy, R, MFE/MAE, targets/stops, sessions, and market states;
  do not declare arbitrary winners.
- Trading profiles measure behavior rather than guess personality.
  Personal baselines compare the user with prior self.
- Evidence Meter shows counts and evidence classes, not fake AI confidence.
- Trading Black Box captures reconstructable market inputs, strategy version,
  state, risk, setup, recommendation, evidence, health, and calculation version.
- Session briefing, immutable session-start plan snapshot with explicit later
  revisions, debrief, and Trading Calendar beyond green/red P&L.
- Market data records provider/instrument, market/received timestamps, latency,
  status, supported sequence, and provenance.
- Market Clock accounts for exchange time zone, trading dates, futures sessions,
  maintenance/holidays where supported, and replay time.
  Strategies consume controlled time interfaces; replay cannot see the future.
- Instrument identity distinguishes contracts from continuous series and
  captures exchange, expiry, tick specification, multiplier, and session.
- Analysis records structure/trend/VWAP/volume/liquidity/volatility,
  supply/demand, and significant levels.
- Rule types: OBJECTIVE / DERIVED / DISCRETIONARY / EXPERIMENTAL.
  Strategy promotion: DRAFT → BACKTESTED → SHADOW VALIDATED → PAPER VALIDATED →
  LIVE ASSISTED.
- Journals combine automatic facts with human context; subjective labels are
  not objective facts.
- Explicit verified/observed, user-reported, and subjective provenance.
  Preserve conflicting evidence.
- Corrections retain original, correction, reason, time, source.
  Analytics identify dataset, filters, versions, time range, evidence threshold.
- Description is not prediction. Comparable observations alone do not justify
  a win probability. Predictive claims need validated models and calibration.
- Cold start: education without personal data; cautious observations with
  limited data; meaningful analytics when evidence is established.
- Learning Copilot follows trade → journal → review → pattern → learning,
  triggered by evidence rather than generic lessons.

### Controlled autonomy horizon — not live execution permission

- Automation Readiness explicitly displays prerequisites and lock state.
- Automation Console defines strategy/mode/instrument/session and bounded
  trade, quantity, risk/loss, R:R, safety limits.
- Shadow Agent makes live decisions with zero orders.
- Paper order workflows follow sufficient shadow evidence.
- First live broker stage is read-only balances/positions/orders/fills.
- Broker reconciliation treats broker activity as authoritative;
  mismatch disables automation.
- Confirmation execution needs explicit approval of submission.
- Bounded automation requires a separately authorized account, version,
  instrument, limits, window, stop requirement, and expiration.
  Neither AI nor strategy may raise those limits.
- Independent deterministic Risk Gate and Safety Controller stand between
  strategy and execution. Kill architecture covers manual kill/loss, stale data,
  disconnect/reconciliation, unknown positions/state, strategy/risk exceptions,
  and clock failure. Strategy does not own the broker door.
- Broker adapters isolate provider specifics and credentials from AI, frontend,
  logs, and exports.
- Graduation: OBSERVE → UNDERSTAND → ADVISE → TRACK HUMAN EXECUTION → REPLAY →
  SHADOW → PAPER → LIVE READ-ONLY → CONFIRMATION → BOUNDED LIVE.

## Development waves

| Wave | Approved scope |
|---|---|
| 0 — Baseline | Repository/GitHub, fresh tests, migrations, backup baseline; synchronize safely and record the baseline. |
| 1 — Trust | Backup automation, audit, ownership coverage, membership foundation, portability documentation, system health. |
| 2 — Personal OS | Goal Financial Activity, Planning, Projects, Tasks, Timeline, Attention, Forecasting, Scenarios. |
| 3 — Trading foundation | Instruments/futures identity, clocks/sessions, market-data contracts, provenance, strategy/version architecture, setup lifecycle. |
| 4 — Live intelligence | Live data, analysis, Strategy Engine/HUD, Copilot, Position Watch, alerts. |
| 5 — Evidence | Journal, shadow outcomes, evidence/corrections, Data Health, analytics, personal baseline, strategy comparison. |
| 6 — Laboratory | Replay/Decision Replay, experiments, Shadow Agent, Trading Black Box. |
| 7 — Living Serenity | Readings, WHY/SOURCE/HISTORY, Pulse/Today/Command Center, visualization, activity/relationships, System Console, lineage/command foundations. |
| 8 — Integration/release candidate | Performance, failure/restore/security/ownership/migration/browser testing, degraded modes, documentation, self-hosting readiness, system integration. |

Every wave reinforces the complete horizon; do not implement everything at
once or introduce speculative entities/providers. Preserve existing canonical
financial/reference meaning, ownership safeguards, and the Python-only stack.

Success is finance/goals/planning/projects/portfolio/trading/system health
converging into context → readings → attention → decisions → review → history →
intelligence.