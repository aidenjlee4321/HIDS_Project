# HIDS TODO

## Immediate

- [ ] Update architecture.md to remove remediation.
- [ ] Adopt ECS 9.5.0 as the initial reference.
- [ ] Update event-schema.md.
- [ ] Create schema-design-process.md.
- [ ] Create confidence.md.
- [ ] Update threat-model.md.
- [ ] Establish initial event coverage matrix.

## Schema Research

- [ ] Study ECS Core and Extended fields.
- [ ] Investigate journald event structures.
- [ ] Investigate Linux Audit event structures.
- [ ] Collect representative Ubuntu event fixtures.
- [ ] Map authentication events to ECS.
- [ ] Map process execution events to ECS.

## Implementation

- [ ] Define the machine-readable event schema.
- [ ] Implement event validation.
- [ ] Implement the first journald collector.