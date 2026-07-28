# Agent Knowledge Foundation: AI-Powered Electrical Quoting

> Status: knowledge foundation — implementation of the conversational capture engine is planned for a later phase.
> Companion files:
> - `docs/ai_electrician_quoting_platform_research/ai_electrician_quoting_platform_research.md`
> - `docs/ai_electrician_quoting_platform_research/job_capture_data_model.json`
> - `docs/UK_Domestic_Electrical_Quoting_Knowledge_Base.md`
> - `docs/ai_electrician_quoting_platform_research/uk_domestic_electrical_knowledge_base.json`

---

## 1. Purpose

This document translates the deep research in `ai_electrician_quoting_platform_research` into a working knowledge foundation for AI agents that operate on behalf of human electricians.

The goal is not to replace the electrician. It is to give the agent enough domain expertise to:

1. **Capture requirements safely** — translate vague customer intent into a structured, quotable specification.
2. **Flag compliance issues early** — Part P notifiability, special locations, supply capacity, RCD requirements.
3. **Surface uncertainty honestly** — know when to stop guessing and hand over to a qualified electrician.
4. **Generate a defensible first-pass quote** — material, labour and compliance notes that the electrician can validate, not re-do from scratch.

---

## 2. Core design principles for specialist agents

These principles should be baked into every prompt, eval case and UI copy.

| Principle | What it means in practice |
|-----------|---------------------------|
| **The electrician is the final authority** | The agent recommends; it does not certify. Every quote must carry a clear "electrician to verify on site" caveat for anything uncertain. |
| **Progressive disclosure** | Simple, outcome-oriented questions first. Technical details only after intent is clear. |
| **No jargon without explanation** | If a term like "RCD", "Part P" or "spur" is used, explain it in the same breath. |
| **"I don't know" is always valid** | Missing information should be recorded as `unknown — electrician to verify`, never fabricated. |
| **Compliance is non-negotiable** | Notifiability, special-location rules and supply-capacity warnings are mandatory flags, not suggestions. |
| **Load and distance drive cost** | Two identical-sounding jobs can have very different quotes because of appliance load and cable run length. |
| **Regional and site factors matter** | Property age, floor/wall construction, access and geography are large cost drivers. |
| **Set expectations about exclusions** | Making good, decorating and flooring repairs are almost never included. State this explicitly. |

---

## 3. Three-layer knowledge architecture

The research defines a three-layer model. Agents should reason through it in order.

### Layer 1 — Universal context (ask every time)

Captured by the 11 universal questions in the JSON data model:

```text
UQ-01  Property type
UQ-02  Property age bracket
UQ-03  Floor level of work
UQ-04  Consumer unit location
UQ-05  Consumer unit age
UQ-06  Customer type (owner / tenant / landlord)
UQ-07  Parking availability
UQ-08  Desired timeline
UQ-09  Photo upload
UQ-10  Earthing system (PME / TN-S / TT)
UQ-11  Competent Person Scheme registration
```

These 11 questions explain roughly 40% of the variance in domestic electrical pricing. An agent should never skip them.

### Layer 2 — Job-specific requirements

The JSON data model defines 5 categories and 19 job types, each with specific questions. The agent must:

1. Classify the customer’s intent into the correct job type.
2. Ask the specific questions in order.
3. Use the answers to select the right circuit design, cable size and protection.

Key job-type decision points:

| Job type | Critical question | Why it changes the quote |
|----------|-------------------|--------------------------|
| Additional socket | What will you plug in? | >2kW appliance → dedicated circuit, not spur. |
| Electric shower | kW rating | Determines cable size (6mm² → 16mm²) and breaker (32A → 50A). |
| EV charger | Off-street parking? / Existing large loads? | May make install impossible or trigger DNO upgrade. |
| Consumer unit upgrade | Current board type / future plans | Drives board size and SPD/AFDD options. |
| Bathroom lighting | Which BS 7671 zone? | Determines IP rating and permitted equipment. |

### Layer 3 — Decision logic

The `decision_logic` section of the JSON model contains three rule sets:

- **Notifiability rules** — which jobs must be carried out by a registered electrician and notified to Building Control.
- **Pricing adjustment factors** — percentage modifiers for age, construction, access, urgency and region.
- **Cable sizing rules** — quick-reference cable/breaker/max-length lookups.

Agents should apply these rules automatically and surface the result to the customer as plain-language advice.

---

## 4. Compliance flags every agent must enforce

The following flags are mandatory. They should appear as warnings or blockers in the agent output and in the resulting quote notes.

| Flag | Trigger | Agent behaviour |
|------|---------|-----------------|
| `FLAG-01` | CU > 20 years old | Recommend CU upgrade or inspection. |
| `FLAG-02` | Property > 50 years, no recent EICR | Recommend safety inspection. |
| `FLAG-03` | Bathroom work, no confirmed RCD | State that 30mA RCD is mandatory. |
| `FLAG-04` | Socket for >2kW appliance | Escalate to dedicated circuit; do not quote a spur. |
| `FLAG-05` | Outdoor work, no confirmed RCD | State that RCD protection is mandatory. |
| `FLAG-06` | EV charger + other large loads | Warn that a supply-capacity check / DNO notification may be needed. |
| `FLAG-07` | Storage heater > 30 years old | Warn about possible asbestos and specialist removal. |
| `FLAG-08` | Scotland property, alarms not interlinked | State Scottish interlinking requirement. |
| `FLAG-09` | Socket \u226432A, bathroom, outdoor or EV circuit | State that minimum Type A 30mA RCD is required. |
| `FLAG-10` | HRRB, HMO, care home, student accommodation | State that AFDDs are mandatory on socket circuits \u226432A. |
| `FLAG-11` | Outdoor EV charger on a PME supply | Flag PME earthing risk assessment; TT rod or PEN fault detection may be needed. |
| `FLAG-12` | TT earthing system identified | Flag 30mA RCD on all circuits and SPD recommendation. |
| `FLAG-13` | Notifiable work + non-CPS electrician | Itemise or disclaim the building-control fee (\u00a3200-\u00a3400). |
| `FLAG-14` | EICR C1/C2/FI observations | State remedial work is required and quote it separately. |

---

## 5. Conversational patterns

### 5.1 Progressive disclosure example

```text
Customer: "I want a socket in my bedroom."

Agent:  "No problem. Would you like a single or double socket?"
Customer: "Double, please."

Agent:  "Great. Would you like USB charging built in?"
Customer: "Yes."

Agent:  "What will you mainly plug in — things like a lamp and phone charger, or something bigger like a heater or TV?"
Customer: "Just a lamp and phone charger."

Agent:  "Perfect, that sounds straightforward. Is there an existing socket nearby on the same wall?"
Customer: "Yes."

Agent:  "Thanks. A couple of quick questions about the property so I can estimate the cable run..."
```

### 5.2 Handling "I don't know"

```text
Customer: "I don't know how old my fuse board is."

Agent: "No problem — most people don't know. Based on your property being from the 1980s, it's likely a cartridge-fuse board with no RCD protection, but I'll mark it as 'to be confirmed on site' so the electrician checks when they visit."
```

### 5.3 Setting expectations about exclusions

```text
Agent: "The quote covers the electrical work, testing and certification. It doesn't include making good the walls or redecorating after chasing — that's usually arranged separately."
```

### 5.4 Supply system and Competent Person Scheme

The generic knowledge base identifies two data points that change the technical and administrative route:

| Data point | Why it matters | Customer-friendly explanation |
|------------|---------------|------------------------------|
| **Earthing system** | PME, TN-S or TT drives bonding sizes, whether PME earth can be exported, and SPD/RCD requirements. | "Some properties have an earth rod rather than a shared earth — this affects the type of safety devices needed." |
| **CPS registration** | A non-CPS electrician doing notifiable work forces the customer to pay building control (£200-£400). | "Registered electricians can self-certify the work; otherwise the council charges a separate inspection fee." |

If the customer does not know these, mark them `to be confirmed on site` rather than assume.

### 5.5 Certification cost and time expectations

Build the following into every quote that needs a certificate:

| Certificate | Typical time | Cost to include |
|-------------|-------------|-----------------|
| Full EIC (new installation / rewire) | 30-60 min | £25-50 labour |
| Full EIC (consumer unit change) | 20-40 min | £15-35 labour |
| EIC (single new circuit) | 15-25 min | £10-20 labour |
| MEIWC (single circuit alteration) | 10-15 min | £8-15 labour |
| EICR (domestic, 6-10 circuits) | 2-4 hours on-site + report | £150-300 total |

### 5.6 Common quoting mistakes to avoid

From the knowledge base — these should be checked by the agent before a quote is finalised:

1. **Underestimating cable lengths**: add 10-15% to measured route length.
2. **Forgetting sundries**: clips, screws, connectors, earth sleeving and trunking can add £20-£50 even on small jobs.
3. **Insufficient testing time**: 15-60 minutes of billable time depending on complexity.
4. **Missing access costs**: ladders, floorboards, loft access, chasing and making good.
5. **Forgetting certification costs**: CPS notification, certificate completion and handover.
6. **Not checking supply capacity**: adding a 32A EV charger to an already-loaded board may need a DNO upgrade.
7. **Inconsistent pricing**: always quote from an updated price list, not memory.

### 5.7 Quote documentation expectations

A professional quote should include:

- **Scope of works** — what is included.
- **Itemised or inclusive pricing** — labour, materials, testing.
- **Assumptions** — e.g. "existing installation compliant", "standard access".
- **Exclusions** — making good, decorating, DNO upgrades, building-control fees.
- **Validity period** — typically 30-90 days.
- **Payment terms** — deposit and balance.
- **Estimated duration** and **start timeframe**.
- **VAT status**.

---

## 6. Integration with the current BoQ engine

The current `services/ocerp` BoQ engine is deterministic and material-focused. It is good at producing a BOM once the scope is known, but it does not yet conduct the conversational capture described in the research.

Recommended integration path:

### Phase A — Ingest the knowledge foundation (now)

1. Load `job_capture_data_model.json` at startup for the conversation schema.
2. Run `python -m data_pipeline.knowledge_loader` to chunk and embed:
   - `UK_Domestic_Electrical_Quoting_Knowledge_Base.md`
   - `uk_domestic_electrical_knowledge_base.json`
   - `job_capture_data_model.json`
   into the `quoting_knowledge` Qdrant collection.
3. Use the `universal_questions`, `job_categories` and `decision_logic` sections as structured prompt context.
4. Use the compliance flags to enrich quote `warnings` and `notes`.
5. Call `POST /knowledge/search` from the capture agent to retrieve narrative guidance on demand.

### Phase B — Add a conversational capture step (next phase)

1. Build a lightweight state machine around the three-phase flow:
   - Intent & essentials
   - Site assessment
   - Detail & confirmation
2. At each turn, the agent classifies intent, asks the next required question, and updates a structured `JobCapture` object.
3. When enough information is captured, map the `JobCapture` to a `BoQGenerateRequest` and call the existing OCERP engine.

### Phase C — Improve the BoQ engine with captured context (later)

Once the capture layer exists, the deterministic rules in `requirements.py` should be driven by the captured data rather than by keyword heuristics:

| Captured fact | Current heuristic | Preferred input |
|---------------|-------------------|-----------------|
| Number of sockets | Regex on description | Explicit count from conversation |
| Room location / special location | Keyword match | Structured location enum |
| Cable run length | Not captured | Distance from CU question |
| Appliance load | Keyword match | Appliance selection |
| CU age / board type | Not captured | Direct answer |
| Property age / construction | Not captured | Direct answers |
| Regional labour rate | Not captured | Postcode / region selection |
| Earthing system | Not captured | Direct answer (UQ-10) |
| CPS registration | Not captured | Direct answer (UQ-11) |

This will reduce the need for the large deterministic rule set and make outputs more accurate.

### Phase D \u2014 Build a declarative rule interpreter (next)

The current `requirements.py` hard-codes ~94 quantity literals and 16 injection methods. The knowledge base should be expressed as a declarative rule book (YAML/JSON) with three tiers:

| Tier | Meaning | Example |
|------|---------|---------|
| **Mandatory** | Must appear in the BoQ if the trigger is true. | 30mA Type A RCBO for a new socket circuit. |
| **Default** | Appears unless the customer opts out or site conditions forbid it. | SPD on a CU upgrade; 10mm\u00b2 main bonding on a PME supply. |
| **Suggestion** | Offered to the customer as an upgrade or recommendation. | AFDDs in an owner-occupied dwelling. |

The engine should read this rule book at startup, apply rules based on the captured `JobCapture` object, and explain every injection to the customer. This replaces the opaque keyword-driven injection in `requirements.py`.

---

## 7. Prompt engineering guidelines

When building prompts for the capture agent:

1. **Include the data model as context.** The JSON file can be injected as a system prompt appendix or retrieved via RAG.
2. **Give the agent a persona.** Use the exact persona in the JSON: friendly, patient, non-technical electrical expert.
3. **Require structured output.** Every response should include:
   - `next_question` (or `ready_to_quote`)
   - `captured_fields` (updated job capture object)
   - `compliance_flags_raised`
   - `clarification_needed` (if any)
4. **Use few-shot examples.** Include 2-3 example conversations covering socket addition, CU upgrade and EV charger.
5. **Evaluate against the research design principles.** Add eval cases that check not just factual correctness but also tone, progressive disclosure and honest handling of uncertainty.

---

## 8. Suggested evaluation rubric

Any future capture agent should be tested against:

| Category | Pass criteria |
|----------|---------------|
| **Intent classification** | Correctly maps customer input to one of the 19 job types ≥90% of the time on a held-out test set. |
| **Compliance** | Raises the correct Part P / special-location / RCD flag on 100% of cases where it is required. |
| **No hallucination** | Never fabricates answers to questions the customer did not answer. Unknowns are marked `to be confirmed on site`. |
| **Progressive disclosure** | First 2-4 questions are simple and outcome-oriented; technical questions appear only after intent is clear. |
| **Jargon-free** | Explains every technical term it uses. |
| **Load safety** | Correctly escalates high-load appliances to dedicated circuits. |
| **Quote reasonableness** | Generated quotes fall within the typical price ranges for the job type, adjusted for captured site factors. |
| **Protection-device flags** | Correctly flags Type A RCD, AFDD and SPD requirements where applicable. |
| **Exclusion clarity** | States that making good / decorating is not included. |

---

## 9. Immediate next steps

1. **Review the JSON data model** (`job_capture_data_model.json`) and refine job types/questions for your most common enquiry types.
2. **Build a minimal conversational prototype** for one job type (e.g. socket addition) using the three-phase flow and the data model.
3. **Connect the prototype to OCERP** so that a captured job specification generates a BoQ and quote.
4. **Run evals** against the rubric above before expanding to more job types.

---

## 10. Key references

- `docs/ai_electrician_quoting_platform_research/ai_electrician_quoting_platform_research.md`
- `docs/ai_electrician_quoting_platform_research/job_capture_data_model.json`
- `docs/ai_electrician_quoting_platform_research/uk_domestic_electrical_knowledge_base.json`
- `docs/UK_Domestic_Electrical_Quoting_Knowledge_Base.md`
- `docs/ai_electrician_quoting_platform_research/job_taxonomy_tree.png`
- `docs/ai_electrician_quoting_platform_research/question_flow_socket.png`
- `docs/ai_electrician_quoting_platform_research/pricing_benchmarks.png`
- `docs/ai_electrician_quoting_platform_research/regional_pricing.png`
