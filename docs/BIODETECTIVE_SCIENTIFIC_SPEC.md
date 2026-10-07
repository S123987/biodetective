# BioDetective AI: V0 Scientific Specification

**Status:** Research and engineering specification  
**Project:** CST-UP Engineering Students Project Grant Scheme  
**Product identity:** Evidence-grounded causal intelligence for biological claims

## 1. Purpose

BioDetective is an AI-assisted research platform for examining biological claims through structured claims, competing causal hypotheses, source-linked evidence, and explicit uncertainty. Its central question is:

> What exactly is claimed, which explanations could account for it, what evidence bears on each explanation, where does that evidence conflict, and what remains uncertain?

The system should help a researcher inspect how an assessment was formed. It must not present fluent generated text as a substitute for evidence.

## 2. Scope and non-goals

### In scope

- Decompose a user claim into testable biological relationships and context.
- Generate multiple candidate explanations, including indirect and confounding alternatives.
- Retrieve candidate sources from scientific literature services.
- Extract study-level findings while preserving their source and extraction provenance.
- Classify evidence as supporting, contradicting, or insufficient for a specific proposition.
- Represent biological relationships as graph edges with evidence attached to the edges.
- Report evidence dimensions, disagreements, missing links, and candidate validation studies.
- Evaluate retrieval and evidence assessment against a documented expert-reviewed benchmark.

### Out of scope

- Declaring a biological claim true or false from a score.
- Replacing expert interpretation, systematic review, or experimental validation.
- Treating retrieved search results, abstracts, or model-generated mechanisms as confirmed evidence.
- Presenting a proposed validation experiment as a result or as an automatically approved laboratory protocol.
- Reusing product concepts or architecture from DrugForge or a generic biotech application.

## 3. Scientific operating principles

1. **No source, no evidence-backed conclusion.** Generated factual assertions in a report must link to one or more evidence records and source identifiers. If support cannot be traced, label the statement as a hypothesis or omit it.
2. **Search results are candidates.** A retrieved record is not evidence until its relevance and the study finding have been assessed.
3. **Evidence is proposition-specific.** A paper may support one edge, contradict another, or be insufficient for the full causal claim.
4. **Preserve polarity and disagreement.** Supporting and contradictory findings remain separately visible; they are not silently netted into one number.
5. **Keep context attached.** Organism, tissue or cell model, disease, intervention, comparator, and outcome may change the interpretation of a result.
6. **Separate observation from inference.** Store what the study reports separately from the system's interpretation of whether it bears on a hypothesis.
7. **Show unknowns as unknown.** Missing metadata or inaccessible full text must not be converted into a negative finding or a zero-quality score.
8. **Make methods versioned.** Retrieval configuration, extraction model, classification rubric, score formula, and report generation version must be recorded for each investigation.

## 4. Core workflow

### 4.1 Claim intake and decomposition

The system preserves the user's original wording and proposes a structured interpretation. A claim can be split into multiple atomic relationships when it contains a mechanism chain. Each relationship records direction and causal wording. Ambiguity is shown to the user or carried forward explicitly; the system must not silently resolve materially ambiguous terms.

For example, “Gene X causes increased cancer-cell proliferation” may be represented as a proposed chain such as Gene X → Protein X → Pathway A → proliferation. Those intermediate links are candidate propositions, not established facts.

### 4.2 Competing hypothesis generation

For each claim, generate a small, inspectable set of candidate explanations:

- **Direct:** a proposed mechanism linking the claimed cause to the outcome.
- **Indirect:** a proposed mediated route with one or more intermediate entities.
- **Alternative or confounding:** a factor or context that could produce the observed association without the stated causal link.

Each hypothesis records its assumptions, predicted relationships, relevant contexts, and what observation would distinguish it from alternatives. Hypotheses are search plans and reasoning aids, not evidence. The system should not generate an unlimited list; it should prioritize distinct, testable explanations.

### 4.3 Retrieval and evidence extraction

Search literature sources such as PubMed, Europe PMC, OpenAlex, and Crossref through source-specific adapters. Each search records its query, source, time, and retrieval configuration. Deduplicate by persistent identifiers and metadata while retaining source records.

For each candidate study, extract (where available):

- study question and tested relationship;
- design and study type;
- organism, tissue, cell line, or population;
- intervention or exposure, comparator, and measured outcome;
- direction and magnitude of the reported finding, if stated;
- controls, replication, sample or dataset size, and relevant limitations;
- whether the accessible text was a title, abstract, full text, or structured database record.

The extracted study finding and the system's evidence classification are separate fields. An abstract-only record must be marked as such. When a source cannot support a detailed claim, the system must report the limitation rather than fill in missing methods or results.

### 4.4 Evidence classification

Classify each evidence item relative to one explicitly identified proposition and context:

- **Supporting:** the reported finding is directionally consistent with the proposition and the design can bear on it.
- **Contradicting:** the reported finding is directionally inconsistent with the proposition in the stated context and the design can bear on it.
- **Insufficient / neutral:** the study is relevant but does not resolve the proposition, or the direction/design/context is unclear.
- **Not relevant:** the record does not test or inform the proposition; retain its retrieval record but exclude it from evidence summaries.

Association alone is not labeled direct causal support. Classification must include a rationale and source locator (for example, abstract, section, page, table, or figure when available). An extracted classification should carry a review state such as model-proposed, human-reviewed, or adjudicated.

## 5. Data model

The V0 logical model is implementation-neutral. Identifiers should be stable, and all records should include creation time and schema version.

### 5.1 Investigation and claim

An **Investigation** contains the original question, structured claim, user-selected context, retrieval run, hypotheses, evidence items, graph, score report, and generated report.

An atomic **Claim** should include:

| Field | Meaning |
|---|---|
| `original_text` | Exact user-submitted claim. |
| `subject` / `predicate` / `object` | Normalized entities and relationship, with IDs when confidently mapped. |
| `direction` | Proposed direction of the relationship. |
| `causal_language` | Whether wording asserts causation, association, necessity, sufficiency, or another relation. |
| `organism`, `tissue_or_cell`, `disease` | Biological scope, including explicit unknowns. |
| `intervention`, `comparator`, `outcome` | Experimental or observational context, when applicable. |
| `time_scope` | Relevant temporal context, if specified. |
| `qualifiers` | Dose, condition, subtype, and other claim constraints. |
| `decomposition` | Ordered candidate subclaims or graph path, each with its own status. |
| `ambiguities` | Unresolved terms and parser confidence; confidence is not evidence strength. |

### 5.2 Hypothesis

Each **Hypothesis** contains an ID, type (direct, indirect, alternative/confounding), natural-language description, proposed graph path, assumptions, context, predicted observations, discriminating evidence, retrieval targets, and status. Each proposed edge is explicitly marked as hypothetical until supported by evidence records.

### 5.3 Source and study evidence

Keep bibliographic **Source** records separate from study-level **Evidence** records. A source record includes title, authors, year, venue, DOI/PMID/other persistent identifiers, source URL, retrieval source, and retrieval date. An evidence record refers to a source and includes:

- the proposition and hypothesis it addresses;
- the study finding as extracted, plus a locator and accessible-text level;
- study design, model/population, intervention/exposure, comparator, outcome, and limitations;
- evidence polarity and directness for this proposition;
- extraction and classification rationale;
- method/model version, timestamp, and review state;
- links to any independent cohort, dataset, replication, or related publication when known.

The same paper can yield multiple evidence records when it tests distinct propositions or contexts. A DOI or PMID is preferred where available; a persistent source URL and enough metadata should be retained when no identifier is available.

### 5.4 Evidence graph

Graph nodes represent biological entities or outcomes (for example, genes, proteins, pathways, phenotypes, diseases, and experimental factors). Directed edges represent typed, contextualized propositions. Evidence attaches to edges, not merely to nodes. Each edge exposes separate counts and summaries for supporting, contradicting, and insufficient evidence, along with directness and source coverage.

The graph must distinguish a proposed edge from an evidence-supported edge. A displayed path through multiple edges must not imply that every link, or the complete causal chain, is established. The graph engine should preserve source links and edge context through filtering and export.

## 6. Biological Evidence Score (BES)

### 6.1 Meaning

BES is a transparent, versioned summary of the strength and consistency of the evidence currently retrieved for a specified relationship and context. It is not the probability that the proposition is true, a measure of biological importance, or a universal quality label for a paper.

Scores are calculated separately for supporting and contradicting evidence. Reports show both, plus the amount and coverage of evidence. A single net score must not conceal mixed findings.

### 6.2 Candidate dimensions

The prototype should capture the following dimensions with documented rubrics and retain the underlying study-level annotations:

| Dimension | Operational question |
|---|---|
| **Q — Source and reporting quality** | Are the source, methods, and result sufficiently transparent to assess? Do not use venue prestige as a substitute. |
| **E — Experimental leverage** | How directly can the design test the proposed relationship (for example, perturbation with an appropriate outcome versus indirect association)? |
| **R — Replication** | Has the finding been repeated, and under what conditions? Record within-study repetition separately from independent replication. |
| **I — Independence** | How many genuinely independent teams, datasets, cohorts, or experimental systems contribute? Related papers and reused datasets must not be counted as independent. |
| **C — Consistency** | How directionally consistent are findings after stratifying by biological context and design? |
| **M — Methodological agreement** | Do different suitable methods converge, or does support depend on one assay or design? |
| **S — Study adequacy** | Is the sample, dataset, control strategy, and design adequate for the question? Judge relative to study type, not with one raw sample-size threshold. |
| **T — Evidence currency** | How recently has the relationship been investigated, and are newer findings available? Recency is reported separately and must not by itself upgrade causal strength. |

Use anchored ordinal ratings (including an explicit unknown value) rather than unsupported fine-grained precision. Preserve dimension-level results so users can inspect why a summary changed.

### 6.3 Prototype calculation and safeguards

The first desktop implementation exposes a **pilot polarity-balance index**, not the full BES candidate described above. For each model-classified supporting or contradicting source, it applies a versioned design weight and directness weight. The prototype design weights are genetic perturbation 1.00, experimental 0.90, animal 0.80, clinical 0.80, observational 0.60, computational 0.40, review 0.30, and unknown 0.25. Directness weights are direct 1.00, indirect 0.65, association-only 0.45, and unclear 0.25.

For the retrieved and classified sample, the displayed pilot value is:

`100 × Σ(supporting design weight × directness weight) / Σ(supporting and contradicting design weight × directness weight)`

Insufficient items are excluded from the ratio and reported separately. If no supporting or contradicting items exist, the score is unavailable. The UI displays both polarities, the insufficient count, and the prototype label. This is a weighted share within a retrieved sample; it is not a measure of total evidence strength, replication, source quality, biological truth, or probability. Model classification errors and search coverage can change it substantially.

Before benchmark evaluation, freeze and version the score formula, rubrics, and missing-data handling. Compare the pilot index with expert assessments and report sensitivity. The broader BES may include the eight candidate dimensions above only after each has a documented rubric and the benchmark supports its use. Do not silently set unknown dimensions to zero. Report source counts and accessible-text coverage next to any aggregate.

For each edge, calculate supporting and contradictory evidence summaries independently. Missing dimensions remain unknown; if coverage is too low for a meaningful aggregate, return “insufficient evidence to score” with the available evidence details.

Do not finalize numeric category thresholds (such as “weak” or “strong”) until they have been justified and evaluated with the expert benchmark. Any thresholds displayed during prototyping must be labeled provisional and versioned. The final report should prefer a dimension profile and evidence counts to false precision from a lone 0–100 number.

## 7. Contradictions, weakest links, and missing evidence

### 7.1 Contradiction analysis

When studies disagree, show both directions and their source records. First compare context, including organism, cell type, disease subtype, intervention, dose, comparator, outcome definition, study design, and measurement method. Present possible reasons for disagreement as candidate explanations tied to observed differences; do not assert a reason without evidence.

### 7.2 Weakest link and “What’s Missing?”

For a proposed claim path, identify the edge with the least direct or least adequately covered evidence, not simply the edge with the fewest search hits. Explain which evidence dimensions or contexts are missing. A full-path assessment should reflect the chain's weakest supported proposition and must not imply that strong upstream evidence proves an untested downstream effect.

### 7.3 Next validation

Suggest a validation study only when it follows from a stated uncertainty. Each suggestion should specify the relationship to test, a plausible study design, intervention/comparator, model or population, outcome, key controls/confounders, and the result that would distinguish leading hypotheses. Mark the design as a proposal for expert review; do not present it as a guaranteed result or as a substitute for appropriate scientific and institutional review.

## 8. Report contract

An investigation report should include:

1. the submitted claim and its structured interpretation, including unresolved ambiguity;
2. the scope and context used for retrieval;
3. competing hypotheses and their assumptions;
4. supporting, contradicting, insufficient, and excluded evidence counts;
5. evidence graph with source-linked edge details;
6. support and contradiction assessments with dimension profiles and coverage;
7. strongest and weakest assessed relationships, with reasons;
8. contradictions and context differences;
9. what is established, what remains uncertain, and why;
10. proposed next validation with its discriminating outcome;
11. source list and provenance for every material evidence-backed statement;
12. system versions, retrieval date, and limitations (for example, abstract-only coverage).

## 9. Research evaluation plan

### 9.1 Benchmark construction

Build a documented set of biological claims spanning claim types, causal strength, study designs, and evidence landscapes, including claims with mixed or limited evidence. For each claim, preserve the question, scope, retrieved source set, expert annotations, adjudication record, and data-use constraints. Set benchmark size based on project capacity and the precision needed for the planned comparisons; do not invent a sample size before that plan exists.

At least two qualified reviewers should independently assess a subset or all benchmark claims using a written rubric, with adjudication for disagreements. Record reviewer uncertainty and context assumptions rather than forcing artificial consensus. Separate development and held-out evaluation by claim family and, where feasible, source/dataset to reduce leakage.

### 9.2 Comparisons and metrics

Evaluate distinct system stages rather than only the final report:

- **Retrieval:** precision, recall, and source coverage against an expert-curated relevant-source set.
- **Evidence extraction/classification:** class-wise precision, recall, and F1 for support, contradiction, and insufficient; report macro-averaged measures and disagreement cases.
- **Evidence strength:** rank or ordinal association with expert assessments, plus an appropriate agreement measure for categorical ratings.
- **Calibration:** only if the system emits probabilities; evaluate calibration separately and do not describe BES as a probability.
- **Robustness and auditability:** performance by study type and context, citation/locator completeness, unsupported-claim rate, and sensitivity to retrieval or scoring changes.

Specify the benchmark, annotation rubric, exclusions, model versions, and primary metrics before examining held-out results. Report uncertainty intervals and failure cases. Expert agreement is a reference with its own uncertainty, not an unquestionable biological ground truth.

### 9.3 Research question

Can a transparent, source-linked, multi-dimension evidence assessment of biological relationships agree with expert judgments more consistently and auditably than retrieval plus unstructured AI summarization, while retaining contradictory evidence and identifying unsupported links?

The benchmark can also test whether the BES dimensions and weighting improve agreement, and whether gap-directed validation suggestions match expert-identified uncertainties. These are evaluation questions, not assumed outcomes.

## 10. Implemented web architecture

The current application is a Python/FastAPI web server with a browser interface. It runs on `127.0.0.1:8000` by default; AI inference uses the hosted Google Gemini API. It does not train or host a foundation model on the user's hardware. The scientific workflow remains separate from the user interface so that evidence records and score arithmetic can be inspected:

- **Browser interface:** responsive HTML, CSS, and JavaScript provide chat, claim investigation, light/dark appearance, file attachments, microphone capture, and browser-local conversation history.
- **Hosted model boundary:** the server calls the Gemini API for chat, claim decomposition, and evidence extraction. The `GEMINI_API_KEY` stays in an ignored server-side `.env.local` file and is never sent to the browser. General chat can retrieve scholarly candidates from Europe PMC / PubMed, OpenAlex, and Crossref.
- **Evidence service:** adapters query Europe PMC / PubMed, OpenAlex, and Crossref for bibliographic candidates and available abstracts. Deduplication retains the indexes that returned each record.
- **Document and voice input:** PDF, DOCX, TXT, Markdown, and CSV text is extracted in memory and sent with the user's prompt. Browser microphone audio is sent to Gemini for transcription after the user starts a recording.
- **Graph and BES services:** deterministic application code maps model-proposed classifications to known relationship IDs and calculates the documented pilot polarity-balance index.
- **Model boundary safeguards:** model JSON is parsed and constrained to known article indexes and relationship IDs. Source URLs and score arithmetic come from application records and code, not generated model output.

User prompts, excerpts from selected files, and voice recordings selected for transcription leave the computer for hosted processing. On Google's no-cost API tier, submitted content may be used to improve Google products; users should avoid confidential or unpublished material on that tier. BioDetective does not save files or recordings; conversation history is stored in the browser. The local server binds to loopback by default. A public deployment would need authentication, usage limits, HTTPS, and an explicit retention policy before it is exposed to other users.

## 11. Privacy, access, and reliability requirements

- Treat submitted claims and investigation history as user data; document storage and retention before deployment.
- Respect source-provider terms, licenses, and full-text access restrictions.
- Retain enough source metadata and locators to reproduce an evidence trail where permitted.
- Make failed, partial, or rate-limited retrieval visible; never imply that a search was exhaustive.
- Support export of structured evidence and citations so assessments can be independently checked.
- Keep model prompts, model identifiers, retrieval queries, and score versions with the investigation record, subject to appropriate data handling.

## 12. Delivery roadmap

| Version | Deliverable | Exit evidence |
|---|---|---|
| **V0 — Scientific specification** | This document: definitions, logical model, scoring safeguards, and evaluation design. | Scientific and engineering decisions are documented; open choices are explicit. |
| **V1 — Evidence engine** | Claim intake, Europe PMC retrieval, source management, deduplication, and traceable candidate records. | Reproducible retrieval runs and source records with persistent identifiers or fallback metadata. |
| **V2 — Intelligence engine** | Hosted claim decomposition, competing hypotheses, study extraction, and evidence classification. | Structured outputs retain context, proposition IDs, provenance, uncertainty, and review state. |
| **V3 — Research engine** | Evidence graph, pilot BES, contradiction view, weakest-link analysis, and validation suggestions. | Edge classifications and score arithmetic can be inspected back to their source evidence. |
| **V4 — BioDetective UI** | Browser-based chat workspace, online model connection, source-linked evidence cards, responsive graph view, browser history, and export. | A user can follow claim → hypothesis → evidence → gap in the web app without losing source provenance. |
| **V5 — Grant-ready system** | Expert benchmark, quantitative evaluation, demonstration, and final project documentation. | Held-out results, limitations, failure cases, and reproducible evaluation materials are reported. |

## 13. Decisions to resolve before implementation

These are controlled research decisions, not invitations to add unrelated features:

- initial claim domain and inclusion/exclusion rules for the benchmark;
- provider APIs, rate limits, licensing, and full-text availability;
- entity normalization resources and policy for unresolved identifiers;
- exact annotation rubrics, score aggregation, minimum coverage, and category thresholds;
- benchmark size, reviewer expertise, adjudication process, and held-out split;
- model selection, deployment environment, budget, and data retention;
- whether and when evidence records require human review in the intended demonstration.

Resolve and version these choices before evaluating the corresponding system behavior. Until that work is complete, describe BES and automated evidence labels as candidate methods under validation.

