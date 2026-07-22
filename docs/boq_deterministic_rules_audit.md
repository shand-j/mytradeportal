# BoQ Engine Deterministic Rules Audit

> Date: 2026-06-23  
> Scope: `services/ocerp/ocerp/services/requirements.py`, `resolver.py`, `labour.py`, `pricing.py`, and the default labour schedule.

## 1. Why this matters

The current BoQ engine is a hybrid:

1. An LLM generates an initial reading of the job.
2. A deterministic `RequirementEngine` parses the description, drops most of the LLM’s output, and injects its own mandatory items.
3. A `CatalogueResolver` maps those requirements to supplier SKUs.
4. A pricing/labour layer turns the resolved items into a quote.

The deterministic layer has grown quickly. It now contains **~50+ explicit quantity rules, 60+ controlled concepts, and 30+ resolver hard-reject patterns**. When the rules are right, output quality is high. When they are wrong, the engine silently overrides user intent, over-stocks jobs, or misses obviously needed items (e.g. the recent “add 5 double sockets” quote produced no sockets).

This document surfaces every major rule so we can decide what to keep, what to parameterise, and what to hand back to the LLM / user.

---

## 2. Scope detection (the “if” statements)

`RequirementEngine.__init__` and `labour.py` derive scope flags from simple keyword/regex checks.

| Scope | Trigger | Notes |
|-------|---------|-------|
| `is_rewire` | `\brewire\b` or `\brewiring\b` | Drives the largest set of mandatory rules. |
| `is_partial_rewire` | rewire + `ground/first floor`, `upstairs/downstairs`, `extension` | Caps `rooms` to `max(bedrooms+1, 3)`. |
| `is_cu_upgrade` | `consumer unit upgrade` or verb near `consumer unit/fuse box/distribution board` (within 4 words) | Regex excludes `circuit`/`wire` to avoid false positives. |
| `is_kitchen` | `kitchen` in description | Adds cooker switch, heat detector, cooker cable. |
| `is_extension` | `extension` in description | Adds cooker cable, 3 MCBs, outdoor sockets if `front`+`back`+`socket`. |
| `is_garage` | `garage` in description | Adds garage CU, SWA, isolator. |
| `is_ev` | `ev`, `charger`, or `charge point` | Adds fixed EV bundle (Type A RCD, 32A MCB, 20m SWA, isolator, earth rod, glands). |
| `is_ufh` | `underfloor` or `ufh` | Adds UFH mat, thermostat, 2 MCBs, 25m 4mm cable. |
| `is_hmo` | `hmo` | Forces 6 smoke alarms, 2 CO alarms, 3 emergency lights. |
| `wants_afdd` | `afdd` in description | Upgrades protection to AFDDs. |
| `is_premium` | `premium`, `hager`, `mk`, `brushed chrome/steel` | Used to add USB sockets, dimmers, downlights. |
| `is_mid_range` | `mid` or `mid-range` | Same premium-style add-ons at lower threshold. |
| `is_budget` | `budget`, `standard white`, `white plastic`, `cheap`, `basic` | Used to downgrade RCBOs → MCBs and avoid chrome finishes. |
| `prefers_chrome` | `brushed chrome`, `brushed steel`, `stainless steel` | Sets `finish=chrome` on sockets/switches. |
| `prefers_hager` / `prefers_mk` / `prefers_bg` | brand name in description | Passed as a brand attribute to the resolver. |
| `is_ambiguous` | `len(desc.split()) <= 5` | Adds default 10 sockets + 6 lights if not a rewire. |
| `no_labour` | `no labour`, `materials only`, `material list` | Skips labour lines. |

### Property parsing

| Extracted value | Rule | Risk |
|-----------------|------|------|
| Bedrooms | Word map (`one bed` … `six bed`) + `\d+\s*bed` | Misses `1 bedroom`, `1-bed`. Returns `max(found)`, so can over-count. |
| Rooms | `\d+\s*room(s)?` else `bedrooms + 3` | If no room count given, a 1-bed flat becomes 4 rooms. Drives socket/light targets. |

---

## 3. Mandatory material injection rules

All rules live in `RequirementEngine._add_mandatory()`. They run in a fixed order and often overwrite or ignore the LLM suggestions.

### 3.1 Scope corrections

| Rule | Condition | Action |
|------|-----------|--------|
| Strip CU from extensions/kitchens | `is_extension` or `is_kitchen`, and description does **not** contain `new consumer unit` / `consumer unit upgrade` | Removes any `consumer_unit` requirement. |

### 3.2 Consumer unit (`_consumer_unit`)

| Condition | Added item | Qty | Attributes | Risk |
|-----------|------------|-----|------------|------|
| `is_cu_upgrade` and no CU | Consumer unit | 1 | metal, spd, dual_rcd, brand=hager if mentioned | OK, but forces SPD/dual-RCD even on old boards. |
| `is_rewire` and no CU | Consumer unit | 1 | metal, spd, dual_rcd | OK. |
| `is_rewire` and no main switch | Main switch | 1 | 100A | Adds a second main-switch line on top of a populated CU. |
| `is_cu_upgrade` and no smoke alarm | Smoke alarm | 1 | mains smoke | “Check” is treated as a material line. |
| `is_cu_upgrade` and no heat detector | Heat detector | 1 | heat | Same concern. |
| `is_cu_upgrade` and no back boxes | 1-gang box | 10 | size=1gang | Arbitrary flat number. |
| `is_cu_upgrade` and no back boxes | 2-gang box | 5 | size=2gang | Arbitrary flat number. |

### 3.3 Circuit protection (`_circuit_protection`)

Target MCB/RCBO/AFDD count:

| Scope | Target | Formula |
|-------|--------|---------|
| CU upgrade (non-rewire) | 5 | flat |
| Rewire + `rcbo` in desc | `max(6, bedrooms+3)` | grows with bedrooms |
| Rewire (no rcbo) | `max(4, bedrooms+1)` | grows with bedrooms |
| Extension | 3 | flat |
| Garage | 2 | flat |

Protection type selection:

| Condition | Device |
|-----------|--------|
| `wants_afdd` or `is_hmo` | AFDD |
| `rcbo` in description | RCBO |
| otherwise | MCB |

Override:

| Condition | Action |
|-----------|--------|
| `is_budget` or `is_mid_range`, and `rcbo` not in description, and not `wants_afdd` | Converts all RCBOs to MCBs. |

Extra circuits:

| Trigger | Added item | Qty |
|---------|------------|-----|
| `loft` in desc | `loft_rcbo` | 1 |
| `garage` in desc | `garage_rcbo` | 1 |

**Risk:** Downgrading RCBOs to MCBs for budget/mid-range jobs may produce non-compliant quotes where RCBOs are required by context (e.g. circuits in bathrooms, EV, sheds).

### 3.4 Sockets and lights (`_sockets_and_lights`)

This is the largest source of deterministic material.

#### Rewire targets

| Item | Target formula | Notes |
|------|----------------|-------|
| Double sockets | partial: `max(10, bedrooms×4)`; 1-bed: 10; 2-bed: 16; 3-bed: 24; 4+ bed: 32 | Always double sockets; no single sockets. |
| Light points | `max(8, rooms×2 + 4)` | Chooses downlights if premium/chrome/≥3-bed mid/premium; otherwise ceiling roses. |
| USB sockets | `4` if `usb` in desc; `6` if ≥4-bed premium/mid; `4` if ≥3-bed premium/mid | Hidden premium upsell. |
| Dimmer switches | count from desc if `dimmer`/`dimmable`; else `3` if ≥3-bed premium/mid/downlight | Hidden premium upsell. |

#### Non-rewire explicit counts (`_explicit_counts`)

| Trigger | Added item | Qty | Notes |
|---------|------------|-----|-------|
| Number found near `socket` | Double socket | extracted count | Replaces any existing single/double sockets. |
| Number near `downlight`/`spotlight`/`spot` | Downlight | extracted count | Replaces existing downlights. |
| Number near `batten` (extension/garage only) | Batten light | extracted count |  |

**Risk:** A phrase like *“add 5 double sockets and a single by the door”* extracts `5` and discards the single socket entirely.

### 3.5 Cooker switch (`_cooker_switch`)

| Condition | Added item | Qty |
|-----------|------------|-----|
| `is_rewire` or `is_kitchen` or `is_extension` and no cooker switch | Cooker switch | 1 |

### 3.6 Cables (`_cables`)

| Condition | Cable | Qty | Notes |
|-----------|-------|-----|-------|
| `is_rewire` or `is_extension` | 1.5mm lighting | 50m | flat |
| `is_rewire` or `is_extension` | 2.5mm socket | 80m | flat |
| `is_rewire`/`kitchen`/`extension`/`garage` | 6mm cooker | 20m (15m for kitchen-only) | flat |
| Non-rewire socket addition | 2.5mm socket | `max(20, sockets×12, rooms×20)` | New; better than flat, still heuristic. |

### 3.7 Back boxes (`_back_boxes`)

| Scope | Item | Qty | Notes |
|-------|------|-----|-------|
| Rewire | 1-gang metal box | `max(10, rooms×3 + bedrooms)` | Can be very high for large houses. |
| Rewire | 2-gang metal box | `max(5, double_socket_qty / 2)` | Half the socket count. |
| Non-rewire addition | 2-gang box | double socket qty | 1:1 |
| Non-rewire addition | 1-gang box | single sockets + switches | 1:1 |

### 3.8 Fire and CO (`_fire_and_co`)

| Scope | Items | Formula |
|-------|-------|---------|
| Kitchen-only / extension+kitchen | Heat detector | 1 |
| Rewire (partial) | Smoke alarm | 1 |
| Rewire (full) | Smoke alarm | `max(2, bedrooms+1)` |
| HMO | Smoke alarm | 6 |
| Rewire | Heat detector | 1 if ≤2 bed, else 2 |
| HMO | CO alarm | 2 |
| `carbon monoxide`/`co alarm` in desc, or ≥3-bed premium/mid non-partial | CO alarm | 1 |
| HMO | Emergency light | 3 |

### 3.9 EV circuit (`_ev_circuit`)

Fixed bundle if `is_ev`:

| Item | Qty |
|------|-----|
| Type A RCD | 1 |
| 32A MCB | 1 |
| 6mm SWA | 20m |
| Weatherproof isolator | 1 |
| Earth rod | 1 |
| SWA glands | 2 |

**Risk:** Assumes every EV job is a new outdoor circuit with TT earthing. If the customer already has a TN-C-S supply and spare ways, this bundle is excessive.

### 3.10 Garage (`_garage`)

| Item | Qty |
|------|-----|
| Garage consumer unit | 1 |
| SWA | 20m |
| Weatherproof isolator | 1 |

### 3.11 Outdoor sockets (`_outdoor_sockets`)

| Trigger | Item | Qty |
|---------|------|-----|
| `outdoor socket`, `outside socket`, `garden`, or (`front`+`back`+`socket`) | Outdoor socket | 2 |
| same | SWA | 25m |

**Risk:** A garden lighting job can trigger 2 outdoor sockets because of the word `garden`.

### 3.12 TT earthing (`_tt_earthing`)

| Trigger | Items |
|---------|-------|
| `\btt\b` or `victorian` in desc | Earth rod ×1, bonding clamps ×2, supplementary bonding cable 10m |

### 3.13 Underfloor heating (`_ufh`)

| Item | Qty |
|------|-----|
| UFH mat | 2 |
| Thermostat | 2 |
| MCB | 2 |
| 4mm cable | 25m |

### 3.14 Under-cabinet lighting (`_under_cabinet`)

| Trigger | Item | Qty |
|---------|------|-----|
| `under cabinet`, `under-cabinet`, `under cupboard` | Under-cabinet lights | count from desc, default 3 |
| same | LED driver | 1 |

### 3.15 Ambiguous defaults (`_ambiguous_defaults`)

If description is ≤5 words and not a rewire:

| Item | Qty |
|------|-----|
| Double sockets | up to 10 |
| Ceiling lights | up to 6 |

### 3.16 Cable quantity caps (`_cap_cable_quantities`)

| Cable | Cap |
|-------|-----|
| 1.5mm | 100m |
| 2.5mm | 150m |
| 6mm | 25m |
| 4mm | 50m |
| SWA | 25m |

---

## 4. LLM filtering rules

The engine parses LLM output, then aggressively filters it.

### 4.1 Completely dropped concepts (`_DETERMINISTIC_CONCEPTS`)

These concepts are dropped from the LLM output because the deterministic engine claims authority over them:

`consumer_unit`, `consumer_unit_with_spd`, `fuse_box`, `fusebox`, `distribution_board`, `spd_module`, `mcb`, `rcbo`, `afdd`, `type_a_rcd`, `loft_rcbo`, `garage_rcbo`, `main_switch`, `double_socket`, `single_socket`, `usb_socket`, `dimmer_switch`, `ceiling_light`, `downlight`, `spotlight`, `spot`, `recessed_light`, `ceiling_spotlight`, `batten_light`, `smoke_alarm`, `heat_detector`, `carbon_monoxide_alarm`, `emergency_light`, `cooker_switch`, `lighting_cable_1_5mm`, `socket_cable_2_5mm`, `cooker_cable_6mm`, `ufh_cable_4mm`, `swa_cable`, `weatherproof_isolator`, `earth_rod`, `bonding_clamp`, `supplementary_bonding_cable`, `garage_consumer_unit`, `underfloor_heating_mat`, `thermostat`, `under_cabinet_lighting`, `led_driver`, `spotlight`, `spot`, `cable`, `lighting_cable`, `socket_cable`, `twin_and_earth_cable`, `earth_cable`.

**Risk:** The LLM cannot add a slightly different item (e.g. a specific cooker switch the customer described) unless it uses a concept outside this list. It also cannot correct the deterministic quantity when the user gave a precise count in natural language that `_extract_count_near` misses.

### 4.2 LLM blocklist (`_LLM_BLOCKLIST`)

Dropped concepts/keywords: `testing`, `test`, `certification`, `certificate`, `cert`, `inspection`, `inspect`, `ev_charger`, `ev_charger_unit`, `ev_charge_point`, `charger`, `wall_charger`, `tethered_charger`, `untethered_charger`, `installation`, `install`, `labour`, `labor`.

### 4.3 Bad substrings (`_LLM_BAD_SUBSTRINGS`)

Any LLM concept containing these substrings is dropped:

`connector block`, `terminal block`, `crimp terminal`, `crimp`, `terminal`, `connector`, `chocbox`, `choc box`, `connector box`, `junction box`, `ethernet`, `smart switch`, `smart light`, `cctv`, `camera`, `extension lead`, `cable reel`, `cable tidy`, `hdmi`, `junction box`, `usb charger`, `tower`, `adaptor`, `adapter`, `ceiling light`, `pendant light`, `recessed light`, `chandelier`.

**Risk:** Legitimate items such as `smart switch`, `USB charger`, `ceiling light` and `pendant light` are categorically banned. This forces the engine to produce only “standard” outputs.

### 4.4 Controlled concept roots (`_CONTROLLED_CONCEPT_ROOTS`)

Additional LLM concepts treated as duplicates of deterministic rules:

`consumer unit`, `fuse box`, `fusebox`, `distribution board`, `main switch`, `mcb`, `rcbo`, `afdd`, `rcd`, `spd`, `downlight`, `spotlight`, `spot light`, `ceiling light`, `pendant light`, `recessed light`, `batten light`, `under cabinet`, `undercabinet`, `cabinet light`, `cabinet striplight`, `led strip`, `double socket`, `single socket`, `usb socket`, `dimmer`, `cooker switch`, `light switch`, `smoke alarm`, `heat detector`, `carbon monoxide`, `co alarm`, `swa cable`, `armoured cable`, `earth rod`, `bonding clamp`, `supplementary bonding`, `lighting cable`, `socket cable`, `cooker cable`, `twin and earth`, `back box`, `back_box`, `pattress`, `chocbox`, `choc box`, `connector box`, `junction box`, `terminal block`, `data point`, `data socket`, `network socket`, `cat5`, `cat6`, `cat 5`, `cat 6`, `rj45`, `earth bonding`, `main earth bonding`, `equipotential bonding`, `earthing`, `supplementary bonding`.

### 4.5 Allowed complementary concepts (`_LLM_COMPLEMENTARY`)

These are allowed through even if the deterministic engine already covers the category:

`lamp`, `led_lamp`, `gu10_lamp`, `bulb`, `grommet`, `trunking`, `conduit`, `screw`, `cable_clip`, `cable_gland`, `gland`, `swa_gland`.

**Risk:** Very narrow. The LLM can suggest lamps and fixings but not alternative sockets, switches, cables, or accessories.

---

## 5. Resolver determinism

`resolver.py` maps requirements to catalogue items.

### 5.1 Essential keyword groups (`_ESSENTIAL_GROUPS`)

For these concepts, a candidate must contain at least one keyword from **each** group:

| Concept | Required keyword groups |
|---------|-------------------------|
| `type_a_rcd` | `type a`/`type-a` AND `rcd` |
| `swa_cable` | `swa` OR `armoured` |
| `weatherproof_isolator` | `isolator` |
| `earth_rod` | `earth rod` |
| `bonding_clamp` | `bonding clamp`/`equipotential`/`main bonding` |
| `supplementary_bonding_cable` | `supplementary bonding`/`bonding` |
| `smoke_alarm` | `smoke` |
| `heat_detector` | `heat` |
| `carbon_monoxide_alarm` | `carbon monoxide`/`co alarm` |
| `emergency_light` | `emergency`/`bulkhead` |
| `mcb` | `mcb`/`miniature circuit breaker` |
| `rcbo` / `loft_rcbo` / `garage_rcbo` | `rcbo` |
| `afdd` | `afdd` |
| `consumer_unit` | `consumer unit`/`fuse box`/`fusebox`/`distribution board` |
| `main_switch` | `main switch`/`fused switch` |
| `spd_module` | `spd`/`surge` |
| `garage_consumer_unit` | `garage` |
| `double_socket` | `socket` OR `2-gang`/`2 gang`/`double` |
| `single_socket` | `socket` OR `1-gang`/`1 gang`/`single` |
| `usb_socket` | `usb` |
| `dimmer_switch` | `dimmer` |
| `cooker_switch` | `cooker` OR `45a` |
| `downlight` | `downlight`/`spotlight`/`down light`/`spot light` |
| `ceiling_light` | `ceiling`/`pendant`/`rose` |
| `batten_light` | `batten` |
| `under_cabinet_lighting` | `under cabinet`/`under-cabinet` |
| `metal_back_box_1gang` / `metal_back_box_2gang` | `back box`/`backbox`/`pattress` |
| `led_driver` | `driver` |
| `underfloor_heating_mat` | `underfloor heating` |
| `thermostat` | `thermostat` |
| `lighting_cable_1_5mm` | `1.5mm` AND `twin` |
| `socket_cable_2_5mm` | `2.5mm` AND `twin` |
| `cooker_cable_6mm` | `6mm` AND `twin` |
| `ufh_cable_4mm` | `4mm` AND `twin` |

### 5.2 Hard reject rules (`_hard_reject`)

| Concept | Reject if description contains |
|---------|----------------------------------|
| `consumer_unit` | `blank`, `blank plate` |
| `swa_cable` | `hdmi`, `ethernet`, `cat 5`, `cat5`, `cctv`, `extension lead`, `extension cable` |
| `bonding_clamp` / `main_equipotential_bonding` | `crimp` |
| `double_socket` / `single_socket` / `socket_outlet` | `rj45`, `ethernet`, `cat 5`, `cat5`, `cat 6`, `cat6`, `data`, `usb` |
| `under_cabinet_lighting` | ` pack`, `pack of` |
| `metal_back_box_*` / `back_box` / `pattress` | `junction`, ` adaptable`, `inline` |
| `lighting_cable_1_5mm` / `socket_cable_2_5mm` / `cooker_cable_6mm` | `50m`, `100m`, `reel`, `drum` |
| **Any** | `chocbox`, `choc box`, `connector box`, `connector block`, `terminal block` |

### 5.3 Scoring

`score = 0.7 × keyword_overlap + 0.3 × vector_score`.

- Brand mismatch → score `0` (item excluded).
- No price component in scoring.
- Resolver picks the single highest-scoring candidate above `min_score=0.15`.

**Risk:** Because price is ignored, a vector-popular expensive item can beat a cheaper, equally relevant item. This is what happened with the “Matt White” decorative sockets.

---

## 6. Labour determinism

`labour.py` selects a schedule entry from `default_labour_schedule.json` based on the same keyword flags.

| Scope | Schedule entry | Default values |
|-------|----------------|----------------|
| Rewire 1-bed flat | `rewire.1_bed_flat` | 4 electrician days, 2 mate days |
| Rewire 2-bed house | `rewire.2_bed_house` | 5 electrician days, 2 mate days |
| Rewire 3-bed house | `rewire.3_bed_house` | 7 electrician days, 3 mate days |
| Rewire 4-bed house | `rewire.4_bed_house` | 9 electrician days, 4 mate days |
| Rewire 5-bed house | `rewire.5_bed_house` | 11 electrician days, 4 mate days |
| Consumer unit upgrade | `consumer_unit_upgrade` | 1 electrician day |
| EV charger | `ev_charger` | 8 electrician hours |
| Extension | `extension` | 2 electrician days, 1 mate day |
| Garage | `garage` | 1 electrician day |
| EICR | `eicr` | 1 electrician day |
| Fault finding | `fault_finding` | 1 electrician hour |
| Anything else | `small_job_default` | 4 electrician hours |

Property-type mapping:

- `property_type` header overrides everything if provided.
- Otherwise: `flat`/`apartment`/`bungalow` → `N_bed_flat`; house with bedrooms → `N_bed_house`; fallback → `3_bed_house`.

**Risk:** A “small job” such as *“replace 10 downlights”* gets 4 hours regardless of ceiling height, access, or dimming complexity. A 6-bed house falls back to the 3-bed schedule.

---

## 7. Pricing determinism

`pricing.py` is largely formulaic and tenant-driven:

- Material unit price = catalogue `unit_price` × `(1 + markup_percent/100)`.
- Labour line total = rate × quantity.
- VAT applied at tenant `vat_rate`.
- Minimum charge adjustment if subtotal < tenant `minimum_charge`.

No hard-coded money values. The only deterministic quirk is that the description of `loft_rcbo`/`garage_rcbo` appends the requirement note.

---

## 8. Audit findings and risk ratings

| # | Finding | Risk | Why |
|---|---------|------|-----|
| 1 | **Flat cable quantities** (50m / 80m / 20m) for rewires | Medium | Not tied to floor area or socket count. Often right, sometimes wildly off. |
| 2 | **Rewire socket target ladder** (10/16/24/32) | Medium | Assumes every rewire needs a full complement of double sockets; ignores explicit customer counts unless they happen to exceed the target. |
| 3 | **Light target `rooms×2+4`** | Medium | Over-stocks small flats, may under-stock large open-plan spaces. |
| 4 | **Back-box formula `rooms×3+bedrooms`** | Medium-High | For a 5-bed house this is 23 one-gang boxes before sockets are considered. |
| 5 | **LLM cannot override deterministic concepts** | High | User-described specifics (e.g. *“I want chrome USB sockets”*) are silently dropped unless the exact keyword triggers a rule. |
| 6 | **RCBO → MCB downgrade for budget/mid-range** | High | Regulatory context is ignored. Can produce unsafe quotes. |
| 7 | **Brand attribute from description drives SKU, but price is ignored** | High | Premium-looking descriptions get expensive SKUs even when the job is budget. |
| 8 | **`double_socket` essential group allows data/USB sockets** | Fixed recently | Was causing data sockets to satisfy socket requirements. |
| 9 | **`_extract_rooms` assumes `bedrooms+3`** | Medium | Inflates targets when the user does not state room count. |
| 10 | **`is_ambiguous` ≤5 words adds 10 sockets + 6 lights** | Medium | A terse but specific description (e.g. *“EV charger install”*) gets sockets and lights. |
| 11 | **Outdoor socket rule triggers on `garden`** | Medium | Can add sockets to garden-lighting jobs. |
| 12 | **EV bundle always includes earth rod + SWA** | Medium | Assumes TT/outdoor run; not always true. |
| 13 | **Garage bundle always adds garage CU** | Medium | A simple garage supply may not need a sub-CU. |
| 14 | **No price-aware resolver** | High | Expensive items win on vector/keyword score. |
| 15 | **Resolver ignores unit mismatch** (reel vs metre) | Fixed recently | Was pricing 50m reels as per-metre. |
| 16 | **Labour schedule has no property size >5 bed** | Low | Falls back to 3-bed house for large properties. |
| 17 | **`_extract_count_near` only looks within 2 words** | Medium | Misses counts separated by more adjectives. |
| 18 | **`_DETERMINISTIC_CONCEPTS` is very large** | High | The engine claims authority over almost every material category, leaving little room for LLM nuance. |
| 19 | **Bad substrings ban legitimate categories** | Medium-High | Smart switches, USB chargers, pendant lights are categorically excluded. |
| 20 | **No rule traceability in output** | Medium | Users cannot see why an item was added. |

---

## 9. Recommendations

### 9.1 Immediate (low effort, high value)

1. **Add rule provenance to every line item**  
   Expose the `scope_tag`/`notes` in the UI so users can see whether an item came from the LLM, a mandatory safety rule, or a heuristic default.
2. **Stop downgrading RCBOs to MCBs automatically**  
   Make the downgrade a warning or a tenant option, not a default.
3. **Tighten the socket essential group**  
   Require `socket` AND a gang indicator; reject data/ethernet terms (already done — keep it).
4. **Fix the most obvious over-adds**  
   - Back boxes for CU upgrades should not be a flat 10/5.  
   - Rewire cable quantities should scale with socket/light counts or floor area.

### 9.2 Structural (medium effort)

5. **Move rules to a declarative config file**  
   Replace inline `if is_rewire:` blocks with a YAML/JSON rule set, e.g.:
   ```yaml
   - concept: double_socket
     when: is_rewire
     quantity_formula: max(10, bedrooms * 4)
     allow_llm_override: true
   ```
   This makes the rule book auditable and tunable without code changes.
6. **Introduce rule tiers**
   - `mandatory` — safety/regulatory, cannot be overridden (e.g. smoke alarms where required).
   - `default` — sensible starting point, LLM/user can override.
   - `suggestion` — only added if the LLM also mentions it or catalogue match is strong.
7. **Make quantities parametric and configurable**  
   Replace flat numbers with formulas driven by bedrooms, rooms, socket counts, and configurable multipliers stored in tenant settings or a rule file.
8. **Price-aware resolver**
   - Add a price penalty to the score, or pick the cheapest item among the top-N candidates.
   - Respect a `max_unit_price` per spec level (budget/mid/premium).
9. **Allow LLM overrides for controlled concepts**  
   If the LLM output includes a concept in `_DETERMINISTIC_CONCEPTS` but with a different quantity/attribute, treat it as a user override rather than dropping it.

### 9.3 Strategic (high effort)

10. **Retire the “LLM produces a draft, then we ignore it” pattern**  
    Use the LLM to extract explicit user intent (counts, brands, special items, regulatory context) and let the deterministic layer fill only the gaps (safety items, standard accessories, cable). This is the opposite of the current design, where the deterministic layer drives and the LLM is suppressed.
11. **Calibrate against real quotes, not just the golden dataset**  
    Build a regression suite from actual quotes (including the recent “add 5 double sockets” case) and use it to validate rule changes.

---

## 10. Suggested rule-book file

A good first step is to create `services/ocerp/ocerp/data/domestic_electrical_rules.yaml` containing the tables above in machine-readable form, then refactor `RequirementEngine` to load and execute those rules. This would turn the ~1,500-line `requirements.py` into a small rule interpreter plus a config file that product/operations can review.

---

## Appendix: counts

| Category | Count |
|----------|-------|
| Scope flags | 17 |
| Mandatory injection methods | 16 |
| Hard-coded quantities (`Decimal("...")` literals in `requirements.py`) | ~94 |
| Concepts the engine claims authority over (`_DETERMINISTIC_CONCEPTS`) | 50 |
| LLM blocklist entries | 18 |
| LLM bad-substring entries | 28 |
| Controlled concept roots | 62 |
| Allowed complementary concepts | 12 |
| Resolver essential groups | 30 |
| Resolver hard-reject rules | 9 |
| Labour schedule entries | 9 |
