---
title: Agent Registry
nexus: wisdom_nexus
type: engram
writing: no
date created: 2026/04/01
date modified: 2026/04/01
---

# Agent Registry

This file lists all defined agents in the system. The orchestrator reads this registry to know which agents exist and how to instantiate them.

## Entry Format

- **agent_id:** Unique identifier (lowercase, no spaces — used in conversation metadata and file paths)
- **Display Name:** Human-readable name
- **Tier:** functional | incarnated
- **Status:** active | suspended | archived
- **Boot File:** Path to the compiled agent boot file
- **Canonical Directory:** Path to the directory containing canonical MindSpec files
- **Created:** Date
- **Last Modified:** Date
- **Description:** One sentence describing the agent's purpose

## Registered Agents

[Entries added as agents are created through the Framework — Agent Identity and Programming]
