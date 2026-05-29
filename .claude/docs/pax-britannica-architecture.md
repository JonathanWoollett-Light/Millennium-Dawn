# Pax Britannica Architecture

The Pax Britannica feature lets the UK restore its empire by summoning the
modern nations that hold former British territory, and by folding territory it
conquers back into regional anchor states. All script objects keep the neutral
`pax_` prefix (triggers, ideas, opinion modifiers, autonomy tiers) — reuse them
if another colonial power (Portugal/Spain/France) is ever added, rather than
cloning per country.

## Where things live

Everything is in the existing ENG/shared files — there are no pax-specific
files:

| Concern | Where |
| --- | --- |
| Subject tiers (Dominion/Colony/Puppet +colored) | `common/autonomous_states/MD_british_autonomies.txt`, gated by `pax_subject_overlord` in `common/scripted_triggers/99_ENG_scripted_triggers.txt` |
| Subject-tier icons | `interface/MD_autonomy_icons.gfx` — `GFX_autonomy_{dominion,colony,puppet}{,_colored}_icon` reuse the generic associated/satellite/puppet-state art (no bespoke .dds) |
| Economic-pressure ideas + the subject resource buff | `common/ideas/05_united_kingdom.txt` (`pax_*_idea`, incl. `pax_colonial_extraction_idea`) |
| Diplomatic modifiers | `common/opinion_modifiers/ENG.txt` (`pax_antagonized_opinion`, `pax_blockade_opinion`, `pax_imperial_threat_opinion`) |
| Colony cosmetic tags + flags + loc | `common/countries/cosmetic.txt` (13 `<TAG>_british_colony`, one per regional primary), flags in `gfx/flags/{,medium/,small/}`, loc in `MD_countries_cosmetic_l_english.yml` |
| Focus branch (`ENG_the_empire_strikes_back` + regional focuses) | `common/national_focus/05_united_kingdom.txt` |
| Decisions (`ENG_pax_britannica_category`) | `common/decisions/05_ENG_decisions.txt` |
| Events (`ENG_pax_britannica` namespace) | `events/05_united_kingdom.txt` |
| Scripted effects (summons, consolidation, SoE update) | `common/scripted_effects/99_ENG_scripted_effects..txt` |
| Scripted triggers (region lists, `no_major_power`, secondaries) | `common/scripted_triggers/99_ENG_scripted_triggers.txt` |
| `ENG_state_of_the_empire` dynamic modifier | `common/dynamic_modifiers/99_ENG_dynamic_modifiers.txt` |
| Consolidation wiring (`on_puppet`/`on_annex`/monthly backstop) | `common/on_actions/99_ENG_on_actions.txt` |
| Focus/decision/event/idea loc | `localisation/english/MD_focus_ENG_l_english.yml` |
| Region focus icons | `gfx/interface/goals/00_regions/ENG_pax_<region>.dds`, sprites + shine in `interface/goals.gfx` / `goals_shine.gfx` |

## Subject autonomy

- The Pax tiers (Dominion 0.80 > Colony 0.45 > Puppet 0.20, plus `_colored`
  variants) are gated `allowed = { pax_subject_overlord = yes }`.
- **Every non-Pax `autonomy_state` carries `NOT = { pax_subject_overlord = yes }`**
  in its `allowed` block, so a Pax overlord's subjects only ever see the
  Dominion/Colony/Puppet ladder — the generic MD tiers drop out. This is what
  makes demotion behave (a Dominion demotes to Colony, not to the generic
  Associated State at 0.75 that otherwise interleaves between them). `allowed` is
  evaluated dynamically, so the gate takes effect the moment
  `ENG_the_empire_strikes_back` sets `ENG_pax_britannica_unlocked`.
- `ENG_state_of_the_empire` carries a flat `subjects_autonomy_gain` (`-0.15`,
  deliberately **not** scaled by reclaim progress like the other SoE stats) — a
  constant downward pull so the overlord can overwhelm a subject's freedom-seeking.
  Set in `eng_update_state_of_the_empire`.
- `pax_is_pax_subject` (subject sits on a Pax tier) is the target filter for the
  `ENG_pax_develop_extraction` decision. There are no manual tighten/loosen
  decisions — the autonomy ladder is driven by the passive
  `subjects_autonomy_gain` pressure.

## Unlock

`ENG_the_empire_strikes_back` is the parent focus: `available` requires
`nationalist_monarchists_are_in_power` + holding the home isles;
`completion_reward` sets `ENG_pax_britannica_unlocked`, adds the
`ENG_state_of_the_empire` dynamic modifier, runs `eng_update_state_of_the_empire`
+ `eng_convert_subjects_to_colonial`, and fires the global news event
`ENG_pax_britannica.10`.

## Regional reclamation

Each regional focus `ENG_pax_<region>` (one per held region,
`prerequisite = ENG_the_empire_strikes_back`) does the work itself — there are
no reclaim decisions:

- `available` gates on `eng_pax_no_major_power_in_<region>` via a
  `custom_trigger_tooltip` (`ENG_pax_no_major_power_<region>_TT`) that **names the
  region's great/major powers** — they must be militarily subjugated before the
  focus can complete.
- `completion_reward` runs `eng_pax_antagonize_<region>` (opinion hit) and fires
  the summons event `ENG_pax_britannica.1` to every non-ENG, non-subject country
  holding a former-British state in the region. The target chooses: accept
  (`eng_become_dominion_of_eng`), refuse (wargoal + naval blockade), or cede the
  BE states (`eng_cede_be_states`).

The intended loop: militarily defeat the region's major power(s) → consolidation
(below) anchors them → `no_major_power` is satisfied → take the focus → summon the
remaining minor holders.

## Conquest consolidation

Each region has one **primary** anchor nation; the rest are **secondaries**.

| Region | Primary | Region | Primary |
| --- | --- | --- | --- |
| north_africa | EGY | australasia | AST |
| west_africa | NIG | north_america | CAN |
| east_africa | KEN | caribbean | JAM |
| southern_africa | SAF | south_america | GUY |
| middle_east | IRQ | europe | IRE |
| south_asia | RAJ | east_asia | HKG |
| southeast_asia | MAY | | |

- `eng_pax_consolidate_<region>` (13) + the `eng_pax_consolidate_all` dispatcher
  (in `99_ENG_scripted_effects..txt`). When ENG has beaten a region's primary it
  is **released to a puppet if annexed**, set to the **Dominion** tier, given its
  `<primary>_british_colony` cosmetic tag, and flagged `eng_pax_<region>_anchored`.
  Once anchored, every conquered **secondary**'s territory — plus any region BE
  state ENG holds directly — folds into the primary with cores. Idempotent via
  the anchor flag and ownership checks.
- `eng_pax_is_<region>_secondary` membership ORs (multi-member regions only, in
  `99_ENG_scripted_triggers.txt`).
- Wired in `common/on_actions/99_ENG_on_actions.txt`: `on_puppet` + `on_annex`
  (scope-robust — checks ENG on both ROOT and FROM) for immediacy, and
  `on_monthly_ENG` as an **ownership** backstop for transfers that bypass those
  hooks (console, scripted). Ownership-gated, so wartime occupation without a peace
  deal does not trigger it.
- **Known sharp edges:** `is_on_continent`-based `no_major_power` regions
  (europe, east_asia, north_america, south_america, middle_east, australasia) gate
  on *no major power on the whole continent*, which makes Europe/East Asia focuses
  near-unattainable. Primary assignments for IRQ (Middle East), KEN (East Africa)
  and MAY (Southeast Asia) are judgement calls — change the region lists in the
  effect file to re-anchor.

## Cosmetic tags

Only the **13 regional primaries** have `<TAG>_british_colony` cosmetic tags,
flags, and loc, applied automatically by the consolidation effect at the moment
of subjugation. Nations that accept a summons become Dominions but keep their
own flag. There is no manual colonial-flag decision.

## Subject economy

- `ENG_pax_develop_extraction` (in `ENG_pax_britannica_category`): PP-cost,
  365-day re-enable, targets Pax subjects (`is_subject_of = ENG` +
  `pax_is_pax_subject`). Grants the subject the timed `pax_colonial_extraction_idea`
  (`local_resources_factor = 0.15`) for a year — renew to sustain it.
