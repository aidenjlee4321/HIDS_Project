# ADR-005: Initial Platform and User Interface

**Status:** Accepted for initial architecture baseline  
**Date:** November 4, 2026

## Context

The initial product is intended to monitor one individual's Linux computer and provide a browser-based local interface.

## Decision

- Target Ubuntu 26.04 LTS initially.
- Support one distribution initially.
- Use a local web-based dashboard.
- Build the frontend with React and TypeScript, using Vite.
- Expose application functionality through FastAPI.
- Use Server-Sent Events (SSE) initially for live dashboard updates.
- Plan for Debian package installation and systemd service management.

## Rationale recorded in the architecture

The product is initially scoped to one Ubuntu distribution and a local web-based dashboard.

The architecture aims to avoid unnecessary Ubuntu-specific dependencies outside collection and packaging so future distribution support is easier.

## Consequences

- Ubuntu-specific collection and packaging behavior must be isolated where practical.
- The API and browser interface need appropriate local security protections.
- The frontend should be served as part of the installed application; the development server is not the production deployment model.
- Debian packaging and systemd integration are part of the long-term implementation roadmap.

## Open questions

- Exact frontend/API packaging layout.
- Local dashboard authentication mechanism.
- Production static asset serving and upgrade behavior.
