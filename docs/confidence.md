# HIDS Detection Confidence and Evidence Context

**Document version:** 0.3  
**Status:** Initial design baseline  
**Last updated:** November 4, 2026  
**Applies to:** Detection rules, security alerts, and alert investigation

## 1. Purpose

This document defines how HIDS presents the evidence behind a detection and how it communicates uncertainty.

HIDS should help users understand:

- What activity was observed.
- Which detection rule matched.
- Which event records support the detection.
- What information is missing or uncertain.
- Which benign explanations may be plausible.
- What additional context could help interpret the activity.

HIDS should not claim to know whether an activity was malicious merely because a rule matched. Detecting that an event or pattern occurred is different from determining the intent behind it.

**The primary responsibility of HIDS is to present accurate, traceable evidence. The user, or an optional AI assistant given the relevant context, should be able to interpret that evidence.**

## 2. Detection, Severity, and Confidence Are Different

These concepts must not be conflated.

| Concept | Meaning | Example question |
|---|---|---|
| Detection | A configured rule matched an observed event or sequence of events | What behavior matched the rule? |
| Severity | The potential impact if the observed activity represents a security problem | How serious could this activity be? |
| Confidence | An assessment of how strongly the available evidence supports an interpretation | How much does the evidence support this interpretation? |

A rule match confirms that the rule's stated conditions were met. It does not, by itself, prove that an attack occurred.

An alert can describe potentially serious activity while leaving its meaning uncertain. For example, HIDS may reliably observe a successful login after several failed attempts without knowing whether the login was performed by an attacker or by the legitimate user.

HIDS may assign a severity classification as part of a detection rule, but it must not present that classification as proof of malicious intent.

## 3. HIDS Does Not Assign Confidence Scores or Labels

HIDS will not assign numerical confidence scores, percentages, probability estimates, or automatic Low/Medium/High confidence labels.

Security events are highly context-dependent. A score or label could imply a level of certainty that the available evidence does not justify. Different users, systems, and environments may have legitimate reasons for interpreting the same activity differently.

HIDS must not present statements such as:

- "There is an 87% chance this is malicious."
- "Confidence: 92/100."
- "High confidence" as an automatically generated verdict.
- Any other system-generated confidence estimate or categorical confidence judgment.

This is a deliberate design decision, not merely a limitation of the first release.

HIDS should provide evidence and relevant context rather than decide how certain the user should be.

## 4. Evidence HIDS Should Present

Every alert should make its supporting evidence accessible.

Where available, the alert should include or reference:

- The detection rule that matched.
- The observed activity and relevant timestamps.
- The source of each supporting event.
- The relevant user, process, file, service, or network information.
- Related events used by the rule.
- The conditions that caused the rule to match.
- Missing, incomplete, or unreliable information.
- Relevant collection gaps or parsing problems.
- Known benign explanations documented by the rule.

The user should be able to inspect the underlying event records rather than relying only on a short alert description.

HIDS should preserve the distinction between:

1. **Observed facts:** Information directly present in collected event records.
2. **Rule findings:** Conditions that the detection engine evaluated and found to match.
3. **Possible interpretations:** Explanations of what the observed behavior might mean.
4. **Unknowns:** Information that the collected evidence cannot establish.

The interface should make these distinctions understandable.

## 5. Context That Helps Interpretation

HIDS should expose information that helps a user or an AI assistant assess the evidence. It should not automatically combine these factors into a confidence score or label.

### 5.1 Evidence quality

How reliable are the underlying records?

Relevant context includes:

- Whether the event came from a reliable operating-system source.
- Whether the source record was parsed successfully.
- Whether important fields are missing or malformed.
- Whether the event can be associated with a source record or collection identifier.
- Whether the event may be duplicated or reconstructed from incomplete information.

The source and collection path should be visible where practical.

### 5.2 Detection specificity

How distinctive is the observed behavior?

A broad indicator may have many legitimate explanations. A more specific combination of attributes may narrow those explanations.

For example:

- A process executing from a temporary directory is a broad indicator.
- A process executing from an unusual temporary location with an unexpected parent process provides additional context.

Specificity depends on the rule and the normal behavior of the host. The location of an executable alone is not proof of malicious behavior.

### 5.3 Corroborating events

Do other events provide relevant context?

Examples include:

- Multiple authentication failures followed by a successful login.
- Process execution followed by privilege-related activity.
- Creation of an executable followed by its execution.
- A sensitive configuration change associated with an unusual process.

HIDS should show relationships between relevant events. Repeated copies of the same underlying record must not be presented as independent corroboration.

### 5.4 Benign explanations and host context

Could the observed behavior be legitimate?

Examples include:

- Installers executing programs from temporary directories.
- Administrators changing system configuration.
- Automated maintenance tasks modifying files.
- A legitimate user mistyping a password several times before successfully logging in.

Rules should document known benign patterns where practical. Users may also have local context that HIDS cannot know, such as whether a particular process or administrative action was expected.

### 5.5 Evidence completeness

Does the available information provide a sufficiently complete picture?

Relevant limitations include:

- Fields unavailable from the original source.
- Information that should have been collected but is missing.
- Collection interruptions or gaps.
- Clock inconsistencies.
- Incomplete event sequences.
- Events that could not be parsed or correlated.

Missing information must not silently be treated as evidence that an activity did not occur.

## 6. Rule Documentation

Every detection rule should document enough information for a user to understand and evaluate its result.

Each rule should specify:

1. **Detection objective:** What behavior is the rule intended to identify?
2. **Match conditions:** What exact conditions cause the rule to trigger?
3. **Required evidence:** Which fields or events are necessary for the rule to operate?
4. **Limitations:** What cannot be established from the rule's evidence?
5. **Benign explanations:** What legitimate activities may match the rule?
6. **Supporting evidence:** Which event records should be attached to the alert?
7. **Tests:** Which positive, negative, and ambiguous cases validate the rule?

Rules should describe what they detect, not claim more than their conditions establish.

### 6.1 Illustrative example: temporary-directory execution

A rule may detect a process executing from a temporary directory.

The alert should explain:

- The executable path.
- The process ID and parent process ID, if available.
- The executing user.
- The event source and timestamp.
- Why the rule considers the location noteworthy.
- Whether related process or filesystem events were observed.
- What information is unavailable.

The rule can accurately report that the execution matched its conditions. It should not conclude that the process is malware solely because it ran from a temporary directory.

## 7. User and AI-Assisted Interpretation

The interpretation of an alert may depend on information outside the event records.

For example, a user may know that:

- They intentionally installed a particular application.
- A process belongs to software they recently configured.
- A system change was part of planned maintenance.
- A login came from a device they own.

HIDS should make it possible for the user to consider this context alongside the collected evidence.

In the future, an AI assistant may help explain alerts or compare competing interpretations. To support this safely, HIDS should be able to provide the assistant with:

- The alert and matching rule.
- The supporting event records.
- Relevant event-source information.
- Known limitations and missing fields.
- Related events within the relevant time window.
- Relevant user-provided context, if the user chooses to supply it.

AI-generated interpretations must remain distinguishable from facts collected by HIDS. An AI assistant should explain its reasoning, identify uncertainty, avoid inventing missing information, and allow the user to reach a different conclusion.

AI interpretation is a possible future feature. The initial HIDS detection engine must not depend on an AI service to collect events or generate rule matches.

## 8. ECS and HIDS Representation

HIDS uses Elastic Common Schema (ECS) as its foundational event data model.

Confidence is an interpretation, not a raw operating-system event property or a deterministic property of a rule match. HIDS should not add a system-generated confidence field to raw events or alerts.

The initial alert representation should prioritize storing and presenting:

- The matched rule identifier and description.
- The rule's match conditions.
- References to supporting events.
- Relevant source and collection metadata.
- Known limitations and missing evidence.
- The rule's severity classification, where applicable.

Any HIDS-specific alert fields should be defined in the HIDS custom namespace and documented separately from raw ECS event fields.

Do not use `event.severity` or `event.risk_score` as substitutes for confidence. Those ECS fields have their own meanings.

If user assessments or AI-generated interpretations are added in the future, they must be stored separately from the original event records and deterministic rule findings. Their data model remains future design work.

## 9. Testing and Evaluation

Detection rules and their explanations must be tested against realistic examples.

For each rule, build test cases covering:

- Expected detections.
- Expected non-detections.
- Ambiguous or incomplete evidence.
- Common benign behavior.
- Missing fields.
- Duplicate events.
- Correlated event sequences.
- Collection or parsing failures.

Testing should establish whether:

- The rule matches the intended conditions.
- The alert accurately describes what was observed.
- Supporting event references are correct.
- Missing information is disclosed.
- The explanation does not claim that malicious intent has been proven.

Useful detection-quality measurements include:

- **Precision:** The proportion of generated alerts that are relevant under the test's labeling criteria.
- **False-positive rate:** The proportion of benign test cases incorrectly flagged.
- **Detection coverage:** The proportion of intended test scenarios successfully detected.

These are evaluation metrics for the detection system. They are not confidence scores to display for individual alerts.

## 10. Future Considerations

Potential future improvements include:

- Allowing users to add notes or context to an alert.
- Allowing users to record their own assessment of an alert.
- Providing an optional AI-assisted explanation using the alert's evidence and user-provided context.
- Showing related events in a timeline to make investigation easier.
- Improving rule documentation as real-world false positives are discovered.

Any user assessment or AI interpretation must remain separate from the original event records and deterministic rule findings.

## 11. Design Principles

The following principles govern HIDS evidence presentation and interpretation:

1. HIDS reports observed activity and rule matches; it does not claim to know intent.
2. Detection and severity are distinct from a user's assessment of confidence.
3. HIDS does not assign numerical confidence scores, probabilities, or automatic confidence labels.
4. Evidence should be inspectable and traceable to its source.
5. Rule explanations must describe the conditions that actually matched.
6. Corroboration must not count duplicate records as independent evidence.
7. Missing information must be disclosed, not treated as proof of benign activity.
8. Known benign explanations and limitations should be documented.
9. User context may materially change the interpretation of an event.
10. AI-generated interpretations must be distinguishable from collected facts and rule findings.
11. The user should remain able to make their own assessment.

**The goal is not to tell users how certain they should be. The goal is to give them accurate evidence, relevant context, and clear limitations so they can make an informed judgment.**
