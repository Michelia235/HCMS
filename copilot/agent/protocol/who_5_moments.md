# WHO "My 5 Moments for Hand Hygiene" - Compliance Rules (RAG knowledge base)

This document is the ground-truth protocol the Compliance Reasoner agent uses to
evaluate an event timeline. Reason ONLY from these rules. Cite the event(s) that
trigger each verdict.

## Event vocabulary (must match event_schema.json `type`)

- `hand_hygiene`   : washing with soap/water OR alcohol-based hand rub. Resets hands to CLEAN.
- `glove_on`       : putting on gloves.
- `glove_off`      : removing gloves. Hands are considered potentially contaminated -> needs hand_hygiene.
- `touch_patient`  : direct skin/contact with the patient.
- `touch_surroundings` : touching bed rails, monitors, IV pole, charts near patient. Contaminates hands.
- `aseptic_procedure`  : injection, drawing blood, catheter insertion, wound care, IV line handling.
- `body_fluid_exposure`: contact with blood, secretions, mucous membrane, non-intact skin, after glove_off from such tasks.

## Hand state model

- Hands start UNKNOWN.
- `hand_hygiene` -> hands become CLEAN at that timestamp.
- `touch_surroundings`, `touch_patient`, `body_fluid_exposure`, `glove_off` -> hands become CONTAMINATED.
- Hands must be CLEAN immediately before M1 and M2 actions.

## The 5 Moments (rules)

### M1 - BEFORE touching a patient
Rule: Immediately before a `touch_patient`, the most recent `hand_hygiene` must have
occurred with NO contaminating event (`touch_surroundings`, `body_fluid_exposure`,
`glove_off`) in between.
VIOLATION if: a `touch_patient` happens while hand state is CONTAMINATED or UNKNOWN.

### M2 - BEFORE a clean/aseptic procedure
Rule: Immediately before an `aseptic_procedure`, hands must be CLEAN (hand_hygiene with
no contamination after). Strong practice: hand_hygiene -> glove_on -> aseptic_procedure.
VIOLATION if: `aseptic_procedure` while hands CONTAMINATED/UNKNOWN, OR contamination
occurred between the hand_hygiene and the procedure.

### M3 - AFTER body fluid exposure risk
Rule: After a `body_fluid_exposure` (or `glove_off` following an aseptic/fluid task),
a `hand_hygiene` must occur BEFORE the next `touch_patient` or `touch_surroundings`.
VIOLATION if: any touch event happens after exposure without an intervening hand_hygiene.

### M4 - AFTER touching a patient
Rule: After a `touch_patient` (when the interaction ends), a `hand_hygiene` should occur
before leaving / before the next patient or clean task.
VIOLATION if: a new patient `touch_patient` or `aseptic_procedure` begins without a
`hand_hygiene` after the previous patient contact ended.

### M5 - AFTER touching patient surroundings
Rule: After `touch_surroundings` (without touching the patient), a `hand_hygiene` must
occur before the next `touch_patient`.
VIOLATION if: `touch_patient` follows `touch_surroundings` with no `hand_hygiene` between.

## Severity

- HIGH   : missed M2 (aseptic) or M3 (after body fluid). Direct infection risk.
- MEDIUM : missed M1 (before patient).
- LOW    : missed M4 / M5 (after contact / surroundings).

## Output contract

For each detected opportunity (moment), output:
{ moment: "M1".."M5", status: "compliant"|"violation"|"not_applicable",
  severity: "high"|"medium"|"low"|null,
  evidence_event_ids: [...], explanation: "<1-2 cau, tieng Viet, neu ro timestamp>" }

Also output an overall `compliance_score` = compliant_moments / total_opportunities (0..1).
