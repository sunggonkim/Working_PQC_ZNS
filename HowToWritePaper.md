# How To Write A Systems Paper

This document is a general manual for writing computer systems papers.  It is
not a manual for one project.  Use it to write, diagnose, and rewrite papers for
systems venues such as SOSP, OSDI, NSDI, EuroSys, FAST, ASPLOS, SIGMETRICS,
ICDCS, CCGrid, and CLUSTER.

The local examples come from the accepted-paper drafts under
`Paper/Previous paper`:

- `src_sigmetrics26`: ScaleQsim, a distributed full-state quantum circuit
  simulator.
- `src_icdcs26`: AURORA, a tiered-memory quantum simulation runtime.

The external writing principles come from systems-paper advice by Levin and
Redell, Heiser, Lin Zhong, Swanson, Brown et al., and the Heilmeier questions.
URLs are listed at the end.

This guide is considered complete only if it covers all of the following:

- research method before writing,
- section-level paper structure,
- paragraph-level roles,
- sentence-level templates,
- terminology and word choice,
- figures, tables, and captions,
- evaluation methodology,
- related work and limitations,
- bad/better/best rewrites,
- scoring rubrics and final audits,
- traceability to previous papers and external systems-writing advice.

## The Core Principle

A good systems paper is not a diary of what was implemented.  It is a controlled
argument that convinces a skeptical reader of four things:

1. The problem matters.
2. Existing approaches fail for a specific reason.
3. The new idea changes the design space.
4. The implementation and evaluation prove the claim under a clear scope.

Everything else is supporting material.

The reader should never have to guess the problem from the solution.  The paper
must state the problem directly, explain why it is hard, and show why the
proposed system is the right response.

## The Systems Paper Contract

Before writing sections, write the paper's contract in four sentences:

1. `Problem`: What real systems pressure makes this work necessary?
2. `Gap`: Why do existing systems or obvious designs fail?
3. `Idea`: What is the one structural insight that makes the system work?
4. `Evidence`: What experiments prove the idea and bound its limits?

If these four sentences are weak, no amount of writing polish fixes the paper.

Good examples from the previous papers:

- ScaleQsim's contract: full-state simulation is accurate but memory and
  communication grow with qubits; static or GPU-local simulators fail to scale;
  runtime state-space partitioning and dynamic task mapping distribute the full
  state vector across nodes/GPUs; evaluation compares against Qsim, cusvaer,
  HyQuas, and Atlas over scale and circuit type.
- AURORA's contract: GPU VRAM cannot hold large full-state vectors; static
  GPU-centric systems fail beyond capacity; tiered memory with decoupled logical
  ownership, local residency, asynchronous execution, and adaptive cache control
  extends execution beyond GPU memory; evaluation proves feasibility,
  scalability, time breakdown, and sensitivity.

## Research Method Before Writing

Writing cannot rescue weak research method.  Before drafting the paper, the
project must have a testable shape.

Use this research loop:

1. `Question`: state the systems question in one sentence.
2. `Hypothesis`: state what behavior should change and why.
3. `Prototype`: build the smallest end-to-end system that can exercise the
   hypothesis.
4. `Correctness`: test correctness before performance experiments.
5. `Baseline`: choose the strongest relevant baselines and configure them fairly.
6. `Workload`: choose workloads that match the claim boundary.
7. `Measurement`: collect enough data to show central tendency, tail behavior,
   variability, and resource cost.
8. `Attribution`: use ablation and breakdowns to explain the result.
9. `Scope`: state where the system does not help.
10. `Artifact`: keep scripts and data that reproduce the paper's main figures.

This order matters.  If experiments are designed after the system is finished,
the paper often becomes a defense of an implementation rather than a test of an
idea.

### The Heilmeier Test For Systems Papers

Before writing, answer these questions in plain language:

1. What problem are you solving, and why is it hard?
2. How is it solved today?
3. What is the new technical idea?
4. Why can you succeed now?
5. Who benefits if the idea works?
6. What are the risks, assumptions, and limits?
7. How will you measure progress?
8. What result would convince a skeptical reviewer?

If the paper cannot answer these questions, the introduction will drift and the
evaluation will look arbitrary.

### Methodology Rules From Systems Research Advice

- Levin and Redell's core test: state the new idea clearly, state the exact
  problem, state assumptions, explain alternatives, and avoid irrelevant system
  description.
- Heiser's core test: evaluation must show both benefit in the intended region
  and acceptable cost elsewhere.
- Brown et al.'s core test: a systems paper may be science, engineering, art, or
  a mix; the evaluation must match the type of claim.
- Allman's core test: make the reviewer's job easy; unclear writing and unclear
  plots make rejection more likely even when the idea is decent.
- Artifact-evaluation practice: scripts and artifacts should illustrate claims,
  enable validation, and make the main results reproducible where feasible.
- Practical systems workflow: build a tracer-bullet prototype early and build
  experiment infrastructure before the final system is complete.

## Deep Reading Notes From Previous Papers

This section records the structural reading of the previous papers.  The point
is not to copy their topic.  The point is to copy their argument mechanics.

### ScaleQsim: Section-Level Role Map

| File/lines | Local role | General writing rule |
| --- | --- | --- |
| `1.introduction.tex:1--18` | Domain primer: quantum computing, qubits, superposition, entanglement. | Start only as broad as needed for the target audience. |
| `1.introduction.tex:20--24` | Current platform limit: NISQ devices are unreliable and expensive. | Move quickly from domain to why a systems solution is needed. |
| `1.introduction.tex:27--42` | Method scope: HPC simulation and full-state vector simulation. | State the chosen problem variant before proposing a system. |
| `1.introduction.tex:44--75` | First evidence figure and baseline failures. | Use an early figure to make the gap concrete. |
| `1.introduction.tex:82--110` | Capability table for prior work. | Use tables to position categories, not to dump related work. |
| `1.introduction.tex:114--128` | Distinction: dynamic execution planning and distributed metadata. | State the difference as a mechanism, not just "we are better." |
| `1.introduction.tex:131--138` | Mechanisms and headline results. | End the introduction with concrete contributions and numbers. |
| `2.Background.tex:5--19` | Technique taxonomy and cost pressure. | Background should define the substrate and expose the bottleneck. |
| `2.Background.tex:28--57` | Distributed architecture and static-plan limits. | Background should set up why the design will choose its mechanisms. |
| `3.Design.tex:1--3` | Design thesis: distribute the full state vector, not the circuit. | Open Design with the key structural choice. |
| `3.Design.tex:12--49` | Overall procedure: initialization and execution. | Show the whole system before mechanism details. |
| `3.Design.tex:54--93` | State-space partitioning with inter/intra phases. | Each subsection should own one design problem. |
| `3.Design.tex:101--161` | Target-index generation and state-space metadata. | Use bold micro-headings for procedure steps inside one mechanism. |
| `3.Design.tex:165--232` | Mapping, kernel execution, and synchronization avoidance. | Explain how the mechanism preserves the invariant. |
| `3.Design.tex:237--304` | Adaptive kernel parameter adjustment. | Algorithms belong when they define a reusable decision rule. |
| `3.Design.tex:306--315` | Implementation closure. | Keep implementation concrete and short after Design. |
| `4.Evaluation.tex:6--44` | Setup: machine, circuits, baselines. | Lock methodology before presenting results. |
| `4.Evaluation.tex:49--108` | Single-node SOTA comparison. | Start evaluation with the main baseline comparison. |
| `4.Evaluation.tex:111--289` | Weak/strong scalability and workload breadth. | Use figures to show scale and diversity, then explain causes. |
| `4.Evaluation.tex:292--324` | Extreme scale-out. | Show the outer boundary of the claim. |
| `4.Evaluation.tex:328--358` | Time breakdown. | Attribute wins and costs to mechanisms. |
| `4.Evaluation.tex:363--398` | Fidelity/correctness analysis. | If correctness matters, give a separate measured closure. |
| `4.Evaluation.tex:413--439` | Variability/stability. | Add repeated-run stability when reviewers may suspect noise. |

ScaleQsim's paper is useful because it shows a full systems spine: first prove
that baselines fail, then name the mechanism, then evaluate scale, diversity,
breakdown, correctness, and stability.

### AURORA: Section-Level Role Map

| File/lines | Local role | General writing rule |
| --- | --- | --- |
| `1.Introduction.tex:1st paragraph` | Domain and NISQ limit. | Keep broad context compact. |
| `1.Introduction.tex:2nd paragraph` | HPC simulation and full-state scope. | Define the exact problem variant. |
| `1.Introduction.tex:3rd paragraph` | Exponential memory pressure and GPU VRAM limit. | State the systems bottleneck before the first figure. |
| `1.Introduction.tex:Figure 1 paragraph` | Baseline failure and AURORA's capacity point. | Make the first figure answer "why now?" |
| `1.Introduction.tex:Table 1 paragraph` | Prior-work classes and capability gap. | Group prior work by missing capability. |
| `1.Introduction.tex:final paragraphs` | Decoupled tiered-memory idea, mechanisms, results. | End with idea, mechanisms, and numbers. |
| `2.Background.tex:access-skew figures` | Locality pressure in target subsets. | Motivation figures should make Design feel necessary. |
| `2.Background.tex:80--90` | Bandwidth gap and data locality pressure. | Background measurements should become design requirements. |
| `3.Design.tex:3--14` | Overview plus architecture figure. | Put the design map before component detail. |
| `3.Design.tex:16--27` | Tiered memory state layout. | First mechanism often defines the state abstraction. |
| `3.Design.tex:62--96` | Asynchronous execution pipeline. | Explain how execution hides or controls the dominant cost. |
| `3.Design.tex:131--174` | Two-level cache hierarchy. | Separate policy/mechanism from implementation detail. |
| `3.Design.tex:182--246` | Adaptive resource control. | Algorithms are justified when they set parameters or decisions. |
| `3.Design.tex:291--293` | Implementation. | Keep implementation proportional to its novelty. |
| `4.Evaluation.tex:58--112` | Setup, baselines, exclusions, feasibility. | A strong setup states unavailable baselines honestly. |
| `4.Evaluation.tex:133--260` | Performance with SOTA and circuit breadth. | Compare against SOTA at the claim boundary. |
| `4.Evaluation.tex:262--355` | Weak/strong scalability. | Scalability needs both problem-size and resource-size views. |
| `4.Evaluation.tex:357--392` | Time analysis. | Use breakdowns to explain why the design works. |
| `4.Evaluation.tex:399--484` | Sensitivity: compression, granularity, streams, cache, fidelity. | Sensitivity shows the design is not a single tuned point. |

AURORA's paper is useful because it is tighter than ScaleQsim: it reaches the
technical bottleneck early, uses the first figure to make the memory limit
obvious, and makes each design subsection correspond to an evaluation question.

### What The Line-By-Line Reading Shows

The previous papers use a repeated local grammar:

1. `Claim first`: the paragraph opens with the conclusion or mechanism.
2. `Concrete object`: a figure, table, algorithm, workload, or component is
   named immediately.
3. `Numbers or procedure`: the body gives either measured values or exact
   steps.
4. `Cause`: the paragraph explains why the result or mechanism behaves that way.
5. `Bridge`: the ending sets up the next mechanism, result, or limitation.

When a paragraph violates this grammar, it becomes visibly weaker: it reads like
background filler, implementation inventory, or reviewer defense.

### Source-To-Rule Trace

| Evidence source | Rule extracted into this guide |
| --- | --- |
| ScaleQsim Introduction | Put first evidence figure and capability table before the final contribution paragraph. |
| ScaleQsim Design | Start Design with the structural choice, then expand only mechanisms. |
| ScaleQsim Evaluation | Close performance, scale, breadth, breakdown, correctness, and stability separately. |
| AURORA Introduction | Reach the core systems bottleneck by paragraph 3. |
| AURORA Design | Use architecture figure components as subsection names. |
| AURORA Evaluation | State baselines, exclusions, and feasibility before performance claims. |
| Accepted-paper captions | Reuse caption roles: motivation evidence, architecture, baseline comparison, scalability, breakdown, sensitivity, tail latency, and correctness. |
| Levin/Redell | Make the problem, new idea, assumptions, alternatives, and lessons explicit. |
| Heiser benchmarking advice | Avoid selective benchmarks, relative-only numbers, weak baselines, and hidden overhead. |
| Lin Zhong | Write top-down, quantify claims, avoid surprises, and preserve reader state. |
| Allman | Use readable plots, units, restrained claims, and constructive related-work language. |
| OSDI artifact evaluation | Keep artifacts tied to paper claims and main-result reproduction. |

## Section Grammar

Top systems papers repeat the same core idea several times.  They do not repeat
the same paragraph.  Each section repeats the thesis with a different job.

| Section | Role of the repeated thesis | What the reader should learn |
| --- | --- | --- |
| Title | Problem or problem-plus-approach | What area and pressure the paper addresses. |
| Abstract | Thesis as a result | What was built and what it achieved. |
| Introduction | Thesis as a problem, gap, and insight | Why the paper should exist. |
| Background/Motivation | Thesis as empirical pressure | Why naive or prior approaches are insufficient. |
| Design | Thesis as mechanisms and invariants | How the insight becomes a system. |
| Implementation | Thesis as concrete engineering | What was actually built and what constraints mattered. |
| Evaluation | Thesis as measured answers | Whether the system works, where, why, and at what cost. |
| Related Work | Thesis as positioning | How the work differs without caricaturing prior work. |
| Discussion/Limitations | Thesis as scoped truth | What the paper does not prove and why that is acceptable. |
| Conclusion | Thesis as the final takeaway | What the community should remember. |

The stable nouns should repeat.  The verbs should change.

Example:

- Abstract: "We build X and show Y."
- Introduction: "Existing systems cannot do Y because Z."
- Background: "Measurements show Z is real."
- Design: "X uses mechanisms A, B, and C to address Z."
- Evaluation: "A, B, and C improve Y by N under workload W."
- Discussion: "X does not claim Q because Q is outside the chosen model."

## Paragraph Grammar

Every paragraph needs one job.  Do not mix motivation, mechanism, result,
limitation, and future work in one paragraph.

Common paragraph roles:

| Role | First sentence should do this | Body should do this | Last sentence should do this |
| --- | --- | --- | --- |
| Pressure | State the system pressure. | Give concrete scale, workload, or hardware context. | Explain why the pressure matters. |
| Gap | State what existing systems miss. | Name the failed assumption or bottleneck. | Set up the new idea. |
| Figure interpretation | State the conclusion of the figure. | Give the key numbers and comparison. | Explain the cause. |
| Design mechanism | Name the mechanism and its boundary. | Explain input, decision, invariant, and fallback. | Point to the next mechanism or evaluation. |
| Evaluation result | State the research question answer. | Give numbers, baselines, and conditions. | State the lesson or limitation. |
| Limitation | State the scope boundary. | Explain why the current evidence does not cover it. | Say what would be needed to extend the claim. |

Bad paragraph smell:

- It begins with a vague transition such as "In addition" but does not say what
  claim is being advanced.
- It contains several unrelated numbers.
- It introduces a term before defining why the term matters.
- It ends without a consequence.
- It forces the reader to infer whether the result is good or bad.

## Sentence Grammar

A systems sentence should make the reader's job easy.  Put the actor first, the
action second, and the condition or cause last.

Use this default shape:

```text
Subject + active verb + object + condition/cause.
```

Examples:

- "The cache stores recently used blocks to reduce storage reads."
- "Figure 3 shows that the baseline fails after 40 qubits."
- "This occurs because the static plan cannot adapt to larger state vectors."
- "Unlike the baseline, the new runtime keeps ownership fixed and moves only
  residency."

Avoid this shape:

```text
Due to the existence of multiple constraints and owing to the fact that the
system performs a number of operations, improved performance can be obtained.
```

The bad sentence hides the actor, hides the mechanism, and makes the reader
wait until the end.

### Reusable Sentence Templates

Use these templates when drafting.  Replace the placeholders with concrete
systems terms and numbers.

| Purpose | Sentence template |
| --- | --- |
| Problem | `X becomes difficult when Y because Z.` |
| Gap | `Existing systems handle X, but they assume Y.` |
| First figure | `Figure N shows that X fails/degrades when Y increases.` |
| Mechanism | `Component M takes input I, computes decision D, and outputs O.` |
| Contrast | `Unlike A, B keeps C local / avoids D / exposes E.` |
| Cause | `This happens because M removes / adds / avoids C.` |
| Result | `At workload W, X improves metric M by N over baseline B.` |
| Negative result | `X does not improve Y under condition C because Z dominates.` |
| Scope | `This result shows X under condition C; it does not claim Y.` |
| Transition | `The next mechanism uses this state to decide X.` |

### Sentence Lessons From The Previous Papers

The previous papers rely on a small set of sentence moves:

- `Figure X shows...`: starts a result paragraph with evidence.
- `As shown in Figure X...`: ties prose to a visual object.
- `In contrast...`: states the difference from prior work.
- `This is because...`: explains cause after a number or comparison.
- `Thus...`: turns the explanation into a lesson.
- `For example...`: grounds an abstract mechanism in a concrete case.

These moves are simple, but they work because they preserve reader state.  A
reviewer always knows whether the sentence is making a claim, pointing at
evidence, giving a cause, or stating a consequence.

## Introduction: Paragraph-By-Paragraph Pattern

The introduction is the most important part of a systems paper.  It must sell
the problem, the approach, and the evidence without becoming a long related-work
section.

Use this structure:

1. `P1 Domain pressure`: introduce the real-world or research-domain pressure.
2. `P2 Current limitation`: explain why the obvious platform or status quo is
   insufficient.
3. `P3 Technical problem`: state the systems bottleneck precisely.
4. `P4 First evidence figure`: show the bottleneck or failure mode early.
5. `P5 Prior-work classes`: group prior systems by capability, not paper-by-paper.
6. `P6 Capability table`: use a compact table only if it clarifies the gap.
7. `P7 Distinction`: state what the proposed system does differently.
8. `P8 Mechanism summary`: name two to four mechanisms.
9. `P9 Evaluation preview`: give quantitative headline results.
10. `P10 Contributions`: list concise contributions that map to later sections.

Do not write a long generic history unless the venue audience needs it.  Do not
delay the problem statement until the end of the introduction.

### Previous-Paper Evidence: ScaleQsim Introduction

`Paper/Previous paper/src_sigmetrics26/1.introduction.tex` follows this arc:

1. Lines 1--18: broad quantum-computing context.
2. Lines 20--24: NISQ limitation creates need for classical simulation.
3. Lines 27--42: full-state vector simulation is accurate and chosen as scope.
4. Lines 44--50: Figure 1 appears before the prior-work table.
5. Lines 53--75: figure paragraph explains Qsim/cusvaer/HyQuas/Atlas failure
   modes and positions ScaleQsim.
6. Lines 82--110: Table 1 groups prior systems by capabilities.
7. Lines 114--128: distinction paragraph states dynamic execution planning,
   distributed metadata, and scalable communication.
8. Lines 131--138: contribution/result paragraph gives mechanisms and headline
   speedups.

The useful pattern is not the exact quantum story.  The useful pattern is:
domain pressure, limitation, scoped method choice, first evidence figure,
prior-work capability table, distinction, mechanisms, numbers.

### Previous-Paper Evidence: AURORA Introduction

`Paper/Previous paper/src_icdcs26/1.Introduction.tex` is tighter:

1. Paragraph 1: quantum computing and NISQ limitation.
2. Paragraph 2: HPC simulation as practical platform and full-state simulation
   as scope.
3. Paragraph 3: exponential memory pressure and GPU VRAM limit.
4. Figure 1: scalability failure of GPU-centric baselines.
5. Figure paragraph: concrete baseline failures and AURORA's capacity point.
6. Table 1: prior-work capability comparison.
7. Distinction paragraph: decoupled tiered memory, ownership, local residency,
   and overlapped execution.
8. Final paragraph: three mechanisms and headline results.

This is the cleaner introduction pattern: it reaches the actual systems problem
by paragraph 3 and uses the first figure to make the problem undeniable.

## Abstract

The abstract is not a table of contents.  It is a compressed argument.

Use four sentences:

1. `What/Why`: what problem matters and why now.
2. `Gap`: what existing systems cannot do.
3. `Approach`: what the system changes structurally.
4. `Achievement/Implication`: headline numbers and what they mean.

Do not include:

- a list of all components,
- a limitation ledger,
- local artifact names,
- terms not defined anywhere else,
- vague claims without numbers.

Write the abstract early to force clarity.  Rewrite it after evaluation to avoid
claiming more than the paper proves.

## Background And Motivation

Background is not a textbook chapter.  It teaches only what the reader needs to
believe the problem and understand the design.

Good background does three things:

1. Defines the technical substrate.
2. Shows why the substrate creates pressure.
3. Connects the pressure to the design requirements.

Previous-paper patterns:

- ScaleQsim background first distinguishes amplitude sampling from full-state
  simulation, then explains distributed architectures and why large qubit counts
  require multi-node/GPU organization.
- AURORA background first shows access skew/locality, then uses bandwidth and
  execution-time measurements to prove that tiered memory is not just capacity
  expansion but a latency-management problem.

Rule:

If a background paragraph does not make a later design decision easier to
understand, delete or move it.

## Design

Design is where the insight becomes a system.  It should not be a flat tour of
all implementation files.

Use this structure:

1. `Overview`: one paragraph that states the design idea.
2. `Architecture figure`: a figure with all major components and data/control
   flow.
3. `Procedure`: a short walk through the figure.
4. `Mechanism subsections`: only the important mechanisms become subsections.
5. `Implementation boundary`: keep platform-specific details brief or move them
   to Implementation.

Each design subsection must answer:

1. What problem does this mechanism solve?
2. What inputs does it observe?
3. What decision does it make?
4. What invariant does it preserve?
5. What alternatives were rejected?
6. What evaluation result will later validate it?

### Previous-Paper Evidence: ScaleQsim Design

`src_sigmetrics26/3.Design.tex` uses this shape:

- Section opening: states the main design difference: it does not partition the
  circuit; it allocates the full state vector across nodes/GPUs.
- `Overall Procedure`: Figure 2 plus two phases, Initialization and Execution.
- `Two-phase State Space Partitioning`: inter-partitioning and
  intra-partitioning.
- `Task-based Qubit State Management`: task decomposition, target-index
  generation, state-space metadata.
- `Two-phase Mapping and Kernel Execution`: logical target index to local GPU
  index, then kernel execution.
- `Adaptive Kernel Parameter Adjustment`: dynamic launch configuration.
- `Implementation`: brief engineering closure.

The local `\noindent\textbf{...}` blocks are not decoration.  They act as
micro-headings for procedure steps inside a subsection.

### Previous-Paper Evidence: AURORA Design

`src_icdcs26/3.Design.tex` uses an even clearer mechanism map:

- `Overview of AURORA's Design`: design thesis before details.
- Overall design figure.
- `Tiered Memory State Layout`: logical partitioning, target subset generation,
  decoupled residency management.
- `Asynchronous Execution Pipeline`: per-task coordination, overlapped
  execution, cross-resource execution.
- `Two-level Cache Hierarchy`: GPU cache, host DRAM cache, eviction/scoring.
- `Adaptive Resource Control`: memory hierarchy provisioning and context-aware
  runtime control.
- `Implementation`: short implementation detail.

The lesson is that a design section should be organized by mechanisms that
explain the new idea, not by source-code modules.

## Implementation

Implementation proves the system is real, but it should not replace the design.

Include:

- lines of code or implementation size,
- platform and runtime dependencies,
- nontrivial engineering decisions,
- deviations from the clean design,
- optimizations that matter to evaluation,
- reproducibility-critical details.

Exclude:

- routine code walkthroughs,
- scripts that only generate artifacts,
- flags that are not part of the claim,
- repeated motivation.

If implementation details are necessary for correctness or performance, explain
why.  If they are merely present in the code, omit them.

## Evaluation

Evaluation is not "show that the system works."  It answers the questions raised
by the contributions.

Start every evaluation section by stating the research questions.  Then make
each subsection close one question.

A strong systems evaluation has:

1. `Setup`: hardware, software, workloads, baselines, metrics, repetitions.
2. `End-to-end comparison`: the main claim against real baselines.
3. `Ablation`: which mechanisms explain the result.
4. `Sensitivity`: parameters, workload shape, scale, contention, or failure
   modes.
5. `Overhead/resource analysis`: CPU, memory, space, energy, latency, or tail.
6. `Negative results/scope`: where the system does not win.

### Previous-Paper Evidence: ScaleQsim Evaluation

`src_sigmetrics26/4.Evaluation.tex` follows:

1. `Evaluation Setup`: hardware, benchmarks, and baselines.
2. `Performance in Single-Node with SOTA`: direct comparison.
3. `Multi-Node Scalability`: weak and strong scalability.
4. `Diverse Circuit Comparison`: workload breadth.
5. `Extreme Scale-out`: maximum scale.
6. `Time Analysis`: phase breakdown.
7. `Fidelity Analysis`: correctness/quality.
8. `Performance Variability and Stability`: repeated-run stability.

The paper does not put all results in one table.  It uses figures for each
research question and uses bold result blocks to interpret them.

### Previous-Paper Evidence: AURORA Evaluation

`src_icdcs26/4.Evaluation.tex` follows:

1. `Evaluation Setup`: hardware specification, benchmark, baselines, excluded
   systems, feasibility.
2. `Performance with SOTA`: whether the system reaches scales baselines cannot.
3. `Scalability with SOTA`: weak and strong scaling.
4. `Time Analysis`: which costs dominate and which are hidden.
5. `Sensitivity Analysis`: compression, granularity, streams, cache efficiency,
   fidelity.

AURORA's setup is especially useful: it explains excluded baselines explicitly
instead of pretending every comparison is available.

### Evaluation Writing Rule

Every graph paragraph should have this shape:

1. `Conclusion first`: "Figure X shows that..."
2. `Numbers`: "At workload W, system S improves/degrades by N."
3. `Cause`: "This happens because mechanism M..."
4. `Scope`: "The result holds under condition C; outside C, behavior changes."

If the paragraph has no cause, it is only a result dump.  If it has no numbers,
it is handwaving.  If it has no scope, it overclaims.

## Figures And Tables

Figures carry arguments.  Tables carry compact facts.

Use figures for:

- performance trends,
- tail latency,
- scalability,
- ablations,
- sensitivity,
- breakdowns,
- workload comparisons.

Use tables for:

- hardware/software setup,
- workload lists,
- capability positioning,
- parameter defaults,
- compact correctness matrices.

Figure rules:

- Every figure must make one point.
- The caption should state what the figure proves, not just what it contains.
- Axes need units.
- Baselines and configurations must use names consistent with the text.
- Multi-panel figures should use subfigures when each panel answers a distinct
  part of the question.
- Avoid giant composite figures that hide several results inside one image.

Table rules:

- Do not use a table when a trend matters.
- Do not let a table become a review-response ledger.
- Keep capability tables in the introduction small and structural.
- Keep evaluation tables factual: setup, parameters, or measured matrices.

### Caption Templates

A good caption has two layers: what is plotted, and what the reader should learn.

Use this shape:

```text
Figure N: Metric M for systems A, B, and C under workload W.  The result shows
that claim X holds/fails because trend Y appears.
```

Examples:

- Weak: `Throughput results.`
- Better: `Throughput of three storage systems under 4 KiB synchronous writes.`
- Best: `Throughput of three storage systems under 4 KiB synchronous writes.
  System X is 1.8x faster than Y because batching amortizes per-write metadata
  cost.`

For multi-panel figures:

```text
Figure N: (a) End-to-end latency, (b) mechanism ablation, and (c) sensitivity to
parameter P.  Together, the panels show that mechanism M explains the speedup
and that the benefit remains stable across the tested range.
```

Caption checklist:

- Does the caption name the workload?
- Does it name the metric and unit?
- Does it name the compared systems or configurations?
- Does it state the main lesson?
- Can the figure be understood when printed in grayscale?

### Caption Bank

This bank is general systems-paper guidance.  It is not tied to one project.
Use it to design figures before writing evaluation text.

The reusable pattern is:

```text
Figure N: What is measured, for which systems/configurations, under which
workload or scale.  One sentence states the lesson the reader should remember.
```

#### Caption Levels

| Level | Caption style | Reader effect |
| --- | --- | --- |
| 0 | `Throughput results.` | Useless.  The reader must inspect the plot alone. |
| 1 | `Throughput under random writes.` | Names the metric, but not the comparison or claim. |
| 2 | `Throughput of systems A, B, and C under 4 KiB random writes.` | Makes the plot understandable. |
| 3 | `Throughput of systems A, B, and C under 4 KiB random writes.  System A wins only when batching amortizes per-request metadata cost.` | Makes the plot argumentative. |
| 4 | `Throughput of systems A, B, and C under 4 KiB random writes.  System A wins when batching amortizes metadata cost, but loses when every request must be synchronously published.` | Makes the plot honest by adding scope. |

Most accepted systems-paper captions should be level 2 or 3.  Use level 4 for
the key figures where a limitation or condition matters.

#### Accepted-Paper Caption Roles

The local accepted-paper drafts show a useful spread of caption roles.  The
exact topic is not important; the role is reusable.

| Role | General reusable caption form | Where it appears in strong systems papers |
| --- | --- | --- |
| First motivation result | `Performance/capacity of existing systems under workload W on platform P.  The result exposes bottleneck B.` | Introduction, before contributions. |
| Capability positioning | `Comparison with prior systems across capabilities C1, C2, and C3.` | Introduction or Background. |
| Background bottleneck | `Resource or access pattern that limits existing designs under workload W.` | Motivation and Background. |
| Architecture overview | `Architecture and execution procedure of system X.` | Start of Design. |
| Pipeline overview | `Asynchronous/synchronous execution pipeline of system X.` | Design, after architecture. |
| Data layout | `Layout of logical state/data across nodes, devices, or storage tiers.` | Design mechanism section. |
| Mapping procedure | `Procedure for translating logical request/state X into physical action Y.` | Design mechanism section. |
| Runtime policy | `Adaptive control policy for selecting resource/configuration P.` | Design or Implementation. |
| Workload inventory | `Benchmark workloads and input sizes used in the evaluation.` | Evaluation setup. |
| End-to-end baseline | `Performance comparison between system X and baselines A/B/C across workload W.` | First evaluation result. |
| Weak scalability | `Weak scalability as problem size and resources grow together.` | Scalability subsection. |
| Strong scalability | `Strong scalability as resources increase for a fixed problem size.` | Scalability subsection. |
| Workload breadth | `Performance across diverse workloads using fixed platform/configuration P.` | Generality subsection. |
| Capacity boundary | `Scale-out behavior showing the largest supported problem size or request rate.` | Scale or feasibility subsection. |
| Phase breakdown | `Time/resource breakdown by phases P1, P2, and P3 under workload W.` | Diagnosis subsection. |
| Sensitivity | `Impact of parameter P on metric M under workload W.` | Sensitivity or ablation subsection. |
| Tail distribution | `CDF or tail latency of operation O under configurations A/B/C.` | QoS, latency, or scheduler subsection. |
| Stability | `Run-to-run variability of systems/configurations under workload W.` | Robustness subsection. |
| Correctness or quality | `Correctness/quality/error relative to reference R across workloads or scales.` | Correctness, fidelity, or accuracy subsection. |
| Overhead | `Overhead of mechanism M relative to base configuration B.` | Ablation or implementation-cost subsection. |
| Failure/recovery | `Recovery outcome across injected failure points or fault classes.` | Reliability subsection. |

#### Ready-To-Use Caption Templates

Use these templates as starting points, then replace every placeholder with the
paper's exact nouns.

**Motivation figure.**

```text
Figure N: Performance of existing systems under workload W on platform P.  The
gap between A and B shows that bottleneck C, not component D, is the limiting
factor.
```

This caption belongs early.  It should justify why the paper exists.

**Capability table.**

```text
Table N: Prior systems differ in whether they support capability C1, C2, and
C3.  The proposed problem requires all three simultaneously.
```

This is useful only when the capabilities are structural.  Do not turn it into a
long checklist of minor features.

**Architecture figure.**

```text
Figure N: Architecture and request flow of system X.  Components C1--C3 form the
critical path, while C4 and C5 run off the foreground path.
```

The component names in this figure should become Design subsection names.

**Pipeline figure.**

```text
Figure N: Execution pipeline for operation O.  The pipeline separates foreground
steps S1--S2 from background steps S3--S4 to reduce tail latency.
```

This caption is better than `System overview` because it tells the reader what
movement or ordering matters.

**Data-layout figure.**

```text
Figure N: Data layout across resource tiers R1--R3.  The layout keeps hot state
near resource R1 and moves cold state to R2 when condition C holds.
```

Use this when the core idea is placement, partitioning, caching, sharding, or
replication.

**Algorithm figure.**

```text
Figure N: Decision rule for choosing action A under telemetry T and budget B.
The rule admits work only when it preserves foreground constraint C.
```

Algorithm captions should name the inputs, output, and invariant.

**End-to-end comparison.**

```text
Figure N: End-to-end performance of system X and baselines A/B/C across
workloads W1--Wk.  X improves the median by N but the benefit narrows for Wj
because bottleneck B moves outside mechanism M.
```

This is the main result shape.  It combines number, condition, and cause.

**Tail-latency comparison.**

```text
Figure N: P50, P95, and P99 latency of operation O under foreground workload W
and background pressure P.  Policy M reduces P99 by N by delaying background
work when shared resource R is saturated.
```

Tail captions should say which percentile matters and why.

**Scalability figure.**

```text
Figure N: Weak/strong scalability of system X and baselines A/B as resources
increase from R1 to Rk.  X scales until bottleneck B dominates at scale Rj.
```

Always specify weak or strong scalability.  They are different claims.

**Workload-breadth figure.**

```text
Figure N: Performance across workloads W1--Wk on platform P.  X's advantage is
largest for workload class C and smallest for class D, matching the design
assumption that mechanism M targets bottleneck B.
```

This figure prevents the paper from looking like it was tuned to one benchmark.

**Ablation figure.**

```text
Figure N: Contribution of mechanisms M1--M3 to metric Y under workload W.  M2
accounts for most of the improvement, while M3 mainly protects tail behavior.
```

An ablation caption should identify which mechanism matters most.

**Sensitivity figure.**

```text
Figure N: Sensitivity of metric Y to parameter P.  Performance is stable across
range R and degrades after threshold T because condition C no longer holds.
```

Sensitivity figures need the tested range in the plot or caption.

**Resource-overhead figure.**

```text
Figure N: CPU utilization, memory footprint, and I/O amplification of system X
under representative workloads.  The overhead remains below budget B except
when workload W forces path P.
```

Resource captions should report steady-state overhead, not only peak throughput.

**Failure/recovery figure.**

```text
Figure N: Recovery outcomes across injected cutpoints F1--Fk.  The system
recovers to the previous or latest committed state for all tested cutpoints
within the stated crash model.
```

Reliability captions must name the fault model.  If the figure does not certify
physical power loss, do not imply it.

**Correctness/quality figure.**

```text
Figure N: Output quality of system X compared with reference R across workloads
W1--Wk.  The measured error remains within tolerance T while reducing cost C.
```

Use this when performance could trade off against accuracy, fidelity, or safety.

#### Caption Anti-Patterns

Avoid these forms:

- `Overview of our system.`  Too vague.  Say what flow, boundary, or invariant
  the overview explains.
- `Performance comparison.`  Too vague.  Name metric, systems, workload, and
  lesson.
- `Ablation study.`  Too vague.  Name the removed mechanisms and the result.
- `CDF of latency.`  Incomplete.  Name operation, workload, configurations, and
  tail lesson.
- `Impact of parameter P.`  Incomplete.  Name the metric, range, and stable or
  unstable region.
- Captions that depend only on color: `red is better than blue`.
- Captions that hide important plot facts: log scale, units, normalization base,
  sample count, or excluded failures.
- Captions that become mini-paragraphs with background, motivation, results,
  and limitations all at once.

#### Figure-To-Caption Procedure

Before inserting a figure, answer these questions in order:

1. What claim does this figure prove?
2. What is on the x-axis, and what is the unit?
3. What is on the y-axis, and what is the unit?
4. Which systems, configurations, or mechanisms are compared?
5. What workload, input size, scale, or fault model is used?
6. Is the axis log-scaled, normalized, or truncated?
7. What is the one result sentence the reader should remember?
8. What scope condition prevents overclaiming?

Then write the caption from answers 2--8.  If answer 1 is weak, the figure
should probably be redesigned before the caption is polished.

## Related Work

Related work is not a dumping ground.  It should explain the intellectual map.

Use categories:

1. Systems that solve the same problem with a different boundary.
2. Systems that solve a neighboring problem.
3. Techniques borrowed or adapted.
4. Techniques intentionally not used.

Each related-work paragraph should answer:

- What does this class of work solve?
- What assumption or boundary does it use?
- Why is the present paper different?
- What did the paper learn from it?

Do not write "X does not do our thing" for every cited paper.  That sounds
defensive and disrespectful.  Explain the difference in problem boundary.

## Discussion And Limitations

Limitations are not weakness if they are scoped correctly.  They become weakness
when the introduction overclaims and the discussion quietly retreats.

Write limitations after the reader has seen the contribution.

A good limitation paragraph:

1. States the limit directly.
2. Explains which claim remains valid.
3. Explains what evidence would be required to expand the claim.

Do not use limitations to introduce new claims.  Do not bury a major missing
assumption in one sentence.

## The Reader-State Rule

Reviewers are busy, skeptical, and often outside the exact subfield.  Maintain
their state.

To maintain reader state:

- Define terms before using them.
- Use the same name for the same concept throughout the paper.
- Do not introduce forward references without giving minimal semantics.
- Repeat the core idea with different roles across sections.
- Use figures to reduce memory load.
- Remind readers of assumptions before drawing conclusions from them.
- Do not make readers infer why a number matters.

If a reviewer has to reread three pages to understand a term, the paper is
making them do the author's work.

## The Design-Choice Rule

A good systems paper does not merely describe what was built.  It explains why
those choices were made.

For every important design choice, write:

1. The pressure that forced the choice.
2. The alternatives considered.
3. Why the chosen design fits the pressure.
4. The cost of the choice.
5. The experiment that validates the choice.

This is where many systems papers fail: they present the final system as if it
were inevitable.  A reviewer wants to know why this system, not a simpler one,
not a kernel design, not a library, not a static policy, not a known baseline.

## The Evaluation-Claim Matrix

Before writing evaluation prose, make a table for yourself:

| Claim | Figure/Table | Baseline | Metric | Workload | Expected reviewer doubt |
| --- | --- | --- | --- | --- | --- |
| Main end-to-end benefit | Figure | strongest relevant systems | throughput/latency/etc. | realistic workload | Is the baseline fair? |
| Mechanism matters | Ablation figure | system without mechanism | delta | controlled workload | Is improvement from this mechanism? |
| Scalability | Scale figure | SOTA or self-scale | slope, efficiency | increasing scale | Does it break at larger scale? |
| Robustness | Sensitivity figure | parameter sweep | degradation curve | varied conditions | Is result cherry-picked? |
| Cost | Breakdown/resource figure | lower bound or baseline | CPU/memory/space/time | representative workload | Is overhead hidden? |

Only after this matrix is clear should prose be written.

## Benchmarking Rules

Avoid common benchmarking failures:

- Do not cherry-pick only workloads where the system wins.
- Do not compare against weak or misconfigured baselines.
- Do not report only relative speedups without absolute numbers.
- Do not hide overhead inside a different contract.
- Do not use only microbenchmarks for a broad systems claim.
- Do not claim statistical confidence without enough repetitions.
- Do not omit resource costs when they are relevant.
- Do not use figures whose labels overlap or whose axes are unreadable.

Good evaluation is honest: it shows where the system wins, where it loses, and
why both outcomes make sense.

## Terminology And Word Choice

Use the simplest word that preserves the technical meaning.  A paper sounds more
serious when the terminology is precise, not when the vocabulary is difficult.

### Vocabulary Ladder

Introduce hard terms in this order:

1. Familiar noun.
2. Precise technical term.
3. Acronym, only if it will be used repeatedly.

Example:

```text
The runtime groups bytes into fixed-size encrypted records.  We call each record
a block.  Each block carries an authentication tag.
```

Do not start with an acronym and force the reader to learn it before knowing why
it matters.

### Prefer Simple Verbs

| Avoid | Prefer | Reason |
| --- | --- | --- |
| utilize | use | Shorter and clearer. |
| leverage | use / exploit / benefit from | Pick the exact action. |
| facilitate | enable / allow | Say what becomes possible. |
| demonstrate | show | Clearer for figures and results. |
| exhibit | show / have | Usually simpler. |
| aforementioned | this / that / the previous | Reduces reader load. |
| numerous | many | Simpler. |
| prior to | before | Simpler. |
| due to the fact that | because | Simpler. |
| in order to | to | Simpler. |
| respectively, when avoidable | split the sentence | Long paired lists are easy to misread. |

### Replace Vague Claims With Measured Claims

| Weak phrase | Better phrase |
| --- | --- |
| significantly improves performance | improves throughput by `N%` on workload `W` |
| incurs low overhead | adds `X ms` median latency and `Y ms` p99 latency |
| scales well | maintains `E%` efficiency from `A` to `B` nodes |
| robust performance | varies by less than `N%` across `R` runs |
| lightweight metadata | stores `N bytes` per object / request / block |
| practical deployment | runs on hardware `H` with workload `W` |
| comprehensive evaluation | evaluated on workloads `A`, `B`, and `C` |

If a word can be replaced by a number, use the number.

### Term Creation Rules

Create a new term only when all three are true:

1. The concept appears many times.
2. Existing words are too long or ambiguous.
3. The term maps to a real mechanism, invariant, or metric.

When creating a term:

1. Define it with a familiar noun first.
2. Use one term for one concept.
3. Do not create several near-synonyms.
4. Do not make acronyms carry the argument.

Bad:

```text
The adaptive dynamic hierarchical component performs policy-aware scheduling.
```

Better:

```text
The scheduler assigns each request to CPU or GPU based on queue depth and slack.
```

## Bad, Better, Best Examples

Use this section as a rewrite pattern.  The goal is not to make prose fancy.  The
goal is to make the claim, mechanism, number, and scope visible.

### Problem Statement

Bad:

```text
Modern systems are becoming increasingly complex and therefore require better
solutions.
```

Better:

```text
Modern storage systems must protect data while preserving application latency.
```

Best:

```text
Edge storage systems must protect local sensor and database files without
breaking foreground latency on shared CPU/GPU memory.
```

Why best is better: it names the domain, object, constraint, and platform.

### Prior-Work Gap

Bad:

```text
Prior works do not consider our setting.
```

Better:

```text
Prior encrypted file systems protect file contents but do not control GPU
maintenance work.
```

Best:

```text
Prior encrypted file systems protect file contents, but their block/file
boundaries do not expose accelerator slack or foreground QoS state to the
encryption runtime.
```

Why best is better: it says exactly which boundary is missing.

### Design Mechanism

Bad:

```text
We design an efficient adaptive scheduling architecture.
```

Better:

```text
The scheduler chooses CPU or GPU execution based on workload size.
```

Best:

```text
The scheduler sends foreground 4 KiB writes to the CPU and admits GPU work only
when the batch size exceeds B and telemetry reports slack for at least T ms.
```

Why best is better: it gives the decision rule.

### Evaluation Result

Bad:

```text
Our system significantly improves performance.
```

Better:

```text
Our system improves throughput by 42% over the baseline.
```

Best:

```text
On 4 KiB synchronous writes, our system improves throughput by 42% over baseline
B while increasing p99 latency by 7%; the gain comes from batching metadata
publication.
```

Why best is better: it gives workload, baseline, metric, cost, and cause.

### Negative Result

Bad:

```text
The GPU version is not always better.
```

Better:

```text
The GPU version is slower on small inputs.
```

Best:

```text
The GPU version is slower below 1 MiB because launch and transfer overhead
exceeds AES-GCM compute time; the runtime therefore keeps foreground writes on
the CPU in this range.
```

Why best is better: it converts a weakness into a design rule.

### Limitation

Bad:

```text
We leave many issues to future work.
```

Better:

```text
We do not evaluate physical power loss.
```

Best:

```text
The recovery results cover daemon cutpoints and lower-block fault injection, not
physical power loss.  A power-fault claim would require a harness that controls
device write caches and reboots the machine across interrupted writes.
```

Why best is better: it states what is proven and what evidence would extend it.

### Jargon Filter

Before submitting, search for words that often hide weak writing:

- novel
- significant
- efficient
- robust
- comprehensive
- seamless
- holistic
- framework
- architecture, when it only means code
- mechanism, when no decision rule is described
- optimal, unless an optimization problem and proof are given

These words are not banned, but each use must earn its place.

## Writing Style

Prefer simple, direct sentences.

Use:

- "Figure 4 shows..."
- "This occurs because..."
- "The result indicates..."
- "The mechanism preserves..."
- "The baseline fails when..."

Avoid:

- vague intensifiers: significantly, dramatically, extremely,
- novelty words without substance: novel, first, comprehensive,
- project-internal terms,
- script or artifact names in the main argument,
- long noun stacks,
- passive voice that hides the actor.

Every sentence should either move the argument forward or make a later claim
easier to understand.

## Self-Scoring Rubric

Score each category from 0 to 2 before submission:

- `0`: missing or misleading.
- `1`: present but weak, indirect, or hard to verify.
- `2`: clear, specific, and backed by evidence.

| Category | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Problem | Reader must infer the problem. | Problem appears but late or broadly. | Problem appears early and names pressure, domain, and constraint. |
| Gap | Prior work is listed. | Prior work is grouped but gap is vague. | Prior work is grouped by capability and the missing boundary is explicit. |
| Idea | System is described as components. | Idea is present but not memorable. | One structural insight explains why the design works. |
| Design | Flat component tour. | Mechanisms exist but boundaries blur. | Each subsection owns a mechanism, invariant, fallback, and evaluation closure. |
| Evaluation | Mostly microbenchmarks or self-comparison. | Has baselines but weak ablation/sensitivity. | Fair baselines, realistic workloads, ablation, sensitivity, resources, and limits. |
| Figures | Figures are unreadable or decorative. | Figures show data but captions do not state lessons. | Every figure has a clear claim, units, readable labels, and text interpretation. |
| Language | Dense, jargon-heavy, passive. | Mostly readable but with vague claims. | Simple terms, active verbs, quantified claims, consistent names. |
| Scope | Limitations hidden or apologetic. | Limits stated but disconnected from claims. | Scope explains what is proven and what evidence would expand it. |
| Reproducibility | Scripts/data absent. | Some artifacts exist but not claim-linked. | Main figures can be traced to scripts/data/configurations. |

Interpretation:

- `16--18`: submission-grade writing structure.
- `12--15`: promising but likely to trigger avoidable review concerns.
- `<12`: rewrite the spine before polishing sentences.

Do not average the score mechanically if one category is a hard blocker.  A paper
with a missing problem, unfair baseline, or unreadable figures is not ready even
if other categories look strong.

## Final Pre-Submission Audit

Run this audit after the PDF is built:

1. Read only the title, abstract, first figure, and conclusion.  Can the core
   idea be recovered?
2. Read every figure caption.  Do the captions tell the paper's evidence story?
3. Read every subsection heading.  Do headings form a logical outline?
4. Search for vague words: `significant`, `efficient`, `robust`,
   `comprehensive`, `novel`, `framework`, `seamless`.
5. Search for unsupported absolutes: `always`, `never`, `optimal`, `guarantees`,
   `full`, `complete`.
6. Check that every main claim has a figure, table, theorem, or explicit scope
   paragraph.
7. Check that every major design mechanism appears in evaluation.
8. Check that every negative result or limitation is framed as scope, not hidden
   failure.
9. Check that every graph has units, readable labels, and fair baselines.
10. Check that the artifact path can regenerate or explain every reported
    number.

## Paper Rewrite Workflow

Use this workflow for any systems paper:

1. Write the four-sentence contract.
2. Write the abstract from the contract.
3. Outline the introduction paragraph roles before writing prose.
4. Draw the first evidence figure and the main design figure early.
5. Name only the mechanisms that matter.
6. Map each mechanism to an evaluation question.
7. Build the evaluation-claim matrix.
8. Write figure captions before writing evaluation paragraphs.
9. Remove paragraphs that do not support the contract.
10. Rebuild the PDF and inspect page flow, figures, references, and captions.

## Section-Level Checklist

Use this before submission:

- Title: problem or problem-plus-approach is clear.
- Abstract: four-sentence argument, with numbers.
- Introduction: problem appears early; prior work is grouped; key idea is
  explicit; contributions map to evidence.
- Background: only necessary concepts and motivational measurements.
- Design: architecture figure first; mechanisms, not code modules.
- Implementation: concrete details needed for credibility and reproducibility.
- Evaluation: research questions, fair baselines, realistic workloads,
  ablations, sensitivity, resource costs, negative results.
- Related Work: categories and boundaries, not paper-by-paper dismissal.
- Discussion: honest limits after the positive result.
- Conclusion: one remembered lesson.

## External Sources Checked

- Levin and Redell, "How (and How Not) to Write a Good Systems Paper":
  https://www.usenix.org/conferences/author-resources/how-and-how-not-write-good-systems-paper
- Gernot Heiser, "How to Write a Good Paper":
  https://gernot-heiser.org/talk-howto-paper.pdf
- Lin Zhong, "Tips about writing systems papers":
  https://www.linzhong.org/opinions/writing.html
- Steven Swanson, "The Nuts and Bolts of Writing Papers":
  https://cseweb.ucsd.edu/~swanson/WritingPapers.html
- Brown et al., "The Many Faces of Systems Research":
  https://www.usenix.org/legacy/event/hotos05/final_papers_backup/red_team/red_html/paper.html
- Heilmeier Catechism:
  https://userpages.cs.umbc.edu/finin/home/heilmeyerCatechism.html
- Gernot Heiser, "Systems Benchmarking Crimes":
  https://gernot-heiser.org/benchmarking-crimes.html
- Mark Allman, "A Referee's Plea":
  https://www.icir.org/mallman/plea.txt
- OSDI 2020 Artifact Evaluation Report:
  https://sysartifacts.github.io/osdi2020/report
- Lalith Suresh, "Low-level advice for systems research":
  https://lalith.in/2020/09/27/Low-Level-Advice-For-Systems-Research/
