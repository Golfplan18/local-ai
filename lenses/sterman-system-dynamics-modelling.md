---
lens_id: sterman-system-dynamics-modelling
name: Sterman System Dynamics Modelling
lens_type: analytical-framework
applicability: [systems-dynamics-causal, systems-dynamics-structural]
foundational: true
source: "Sterman, John D. (2000). Business Dynamics: Systems Thinking and Modeling for a Complex World. McGraw-Hill."
date created: 2026-06-17
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - systems
  - dynamics
  - modelling
---

# Sterman System Dynamics Modelling

## Trigger

Invoked when a systems-dynamics mode needs quantitative or semi-formal stock-and-flow discipline. The host mode supplies the system behavior and causal structure; the lens supplies Sterman's modeling checklist.

## Core Structure

System dynamics explains behavior over time through stocks, flows, feedback, delays, nonlinearities, and decision rules.

1. **Reference mode.** The behavior-over-time pattern to explain.
2. **Stocks.** Accumulations that define system state.
3. **Flows.** Rates that increase or decrease stocks.
4. **Feedback loops.** Causal paths that close back on themselves.
5. **Delays.** Time lags between action and effect.
6. **Decision rules.** How actors change flows based on information.
7. **Simulation or mental simulation.** Testing whether the structure can produce the observed pattern.

## Application Steps

1. Define the reference mode: what changes over time?
2. Identify the stocks and flows.
3. Map feedback loops and delays.
4. Specify decision rules or policies controlling flows.
5. Test whether the structure can plausibly generate the observed behavior.
6. Identify policy resistance and leverage points.

## Detection Signals

- The analysis concerns accumulation, delay, oscillation, overshoot, collapse, or policy resistance.
- Causal links are not enough; behavior over time matters.
- A structural systems map may need stock-and-flow precision.
- Proposed interventions may trigger delayed counter-effects.

## Critical Questions

- What stock is accumulating or depleting?
- What flows change that stock?
- Which feedback loops dominate at different times?
- Where are the delays?
- Can this structure generate the observed reference mode?
- Which policy rule creates resistance?

## Common Failure Modes

- **Causal-loop-only trap** - Detection: arrows are drawn but no stocks or flows are named. Correction: identify accumulations and rates.
- **Static explanation** - Detection: the system is described at one moment. Correction: define behavior over time.
- **Delay omission** - Detection: response timing is assumed immediate. Correction: mark time lags.
- **Simulation overclaim** - Detection: model precision is implied without data. Correction: distinguish formal simulation from qualitative structure.

## Source Citations

- Sterman, John D. (2000). *Business Dynamics: Systems Thinking and Modeling for a Complex World*. McGraw-Hill.
- Forrester, Jay W. (1961). *Industrial Dynamics*. MIT Press.

