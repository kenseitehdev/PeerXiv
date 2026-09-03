"""Initial PeerXiv paper taxonomy and descriptive metadata vocabulary.

The vocabulary is intentionally explicit and versioned.  It is small enough to
audit while the first classifier is validated; broader arXiv coverage can be
added without changing the classifier contract.
"""

from __future__ import annotations

from dataclasses import dataclass


TAXONOMY_VERSION = "peerxiv-subjects-2026.08"
METADATA_SCHEMA_VERSION = "peerxiv.descriptive-metadata.v1"


@dataclass(frozen=True, slots=True)
class Taxon:
    code: str
    label: str
    description: str
    terms: tuple[str, ...]
    phrases: tuple[str, ...] = ()
    neighbors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FacetDefinition:
    facet: str
    slug: str
    label: str
    description: str
    terms: tuple[str, ...]
    phrases: tuple[str, ...] = ()


TAXA = (
    Taxon(
        code="cs.AI",
        label="Artificial Intelligence",
        description="Reasoning, intelligent agents, knowledge representation, and general AI systems.",
        terms=("artificial", "intelligence", "agent", "reasoning", "knowledge", "planning"),
        phrases=("artificial intelligence", "intelligent system", "knowledge representation"),
        neighbors=("cs.LG", "cs.CL", "cs.RO", "math.LO"),
    ),
    Taxon(
        code="cs.LG",
        label="Machine Learning",
        description="Algorithms that learn representations, predictions, or decisions from observations.",
        terms=("learning", "classifier", "classification", "training", "prediction", "neural"),
        phrases=("machine learning", "neural network", "recurrent neural", "representation learning"),
        neighbors=("cs.AI", "stat.ML", "cs.CL", "q-bio.NC"),
    ),
    Taxon(
        code="stat.ML",
        label="Machine Learning Statistics",
        description="Statistical foundations, estimation, uncertainty, and validation for learning systems.",
        terms=("statistical", "estimation", "distribution", "regression", "validation", "uncertainty"),
        phrases=("statistical learning", "uncertainty quantification", "predictive validation"),
        neighbors=("cs.LG", "math.ST", "econ.EM"),
    ),
    Taxon(
        code="cs.CL",
        label="Computation and Language",
        description="Computational analysis, representation, and generation of human language.",
        terms=("language", "linguistic", "text", "token", "semantic", "document"),
        phrases=("natural language", "language model", "text classification", "document classification"),
        neighbors=("cs.AI", "cs.LG"),
    ),
    Taxon(
        code="cs.DC",
        label="Distributed Computing",
        description="Distributed, parallel, replicated, and fault-tolerant computing systems.",
        terms=("distributed", "parallel", "replication", "consensus", "node", "cluster"),
        phrases=("distributed system", "partial failure", "fault tolerance", "message passing"),
        neighbors=("cs.SE", "cs.NI", "cs.AI"),
    ),
    Taxon(
        code="cs.SE",
        label="Software Engineering",
        description="Software architecture, implementation, testing, maintenance, and development processes.",
        terms=("software", "architecture", "implementation", "testing", "program", "runtime"),
        phrases=("software engineering", "software architecture", "program analysis"),
        neighbors=("cs.DC", "cs.PL", "cs.CR"),
    ),
    Taxon(
        code="cs.PL",
        label="Programming Languages",
        description="Programming-language semantics, compilers, runtimes, and program transformation.",
        terms=("compiler", "runtime", "semantics", "language", "interpreter", "type"),
        phrases=("programming language", "type system", "operational semantics"),
        neighbors=("cs.SE", "math.LO"),
    ),
    Taxon(
        code="cs.CR",
        label="Cryptography and Security",
        description="Security, privacy, cryptography, threat analysis, and resilient system design.",
        terms=("security", "privacy", "cryptographic", "attack", "threat", "vulnerability"),
        phrases=("information security", "threat model", "access control"),
        neighbors=("cs.SE", "cs.DC"),
    ),
    Taxon(
        code="cs.RO",
        label="Robotics",
        description="Perception, planning, control, and learning for embodied autonomous systems.",
        terms=("robot", "robotics", "control", "trajectory", "sensor", "autonomous"),
        phrases=("robotic system", "motion planning", "autonomous system"),
        neighbors=("cs.AI", "cs.LG", "eess.SY"),
    ),
    Taxon(
        code="cs.NI",
        label="Networking and Internet Architecture",
        description="Network protocols, architectures, measurement, routing, and communication systems.",
        terms=("network", "routing", "protocol", "packet", "bandwidth", "topology"),
        phrases=("network architecture", "computer network", "communication protocol"),
        neighbors=("cs.DC", "eess.SY"),
    ),
    Taxon(
        code="math.DS",
        label="Dynamical Systems",
        description="Evolution, stability, reconstruction, and prediction of mathematical states over time.",
        terms=("dynamical", "state", "trajectory", "stability", "evolution", "movement"),
        phrases=("dynamical system", "state transition", "state reconstruction", "temporal evolution"),
        neighbors=("math.OC", "eess.SY", "math.ST"),
    ),
    Taxon(
        code="math.LO",
        label="Logic",
        description="Formal logic, calculi, proof systems, predicates, and mathematical reasoning.",
        terms=("logic", "calculus", "predicate", "proof", "formal", "rule"),
        phrases=("formal logic", "proof system", "logical calculus"),
        neighbors=("cs.AI", "cs.PL", "math.ST"),
    ),
    Taxon(
        code="math.ST",
        label="Statistics Theory",
        description="Probability, inference, sampling, estimation, and theoretical statistics.",
        terms=("probability", "statistical", "sampling", "estimator", "variance", "confidence"),
        phrases=("statistical inference", "confidence interval", "probability distribution"),
        neighbors=("stat.ML", "math.DS", "econ.EM"),
    ),
    Taxon(
        code="math.OC",
        label="Optimization and Control",
        description="Optimization, decision, control, and constrained state evolution.",
        terms=("optimization", "control", "objective", "constraint", "policy", "decision"),
        phrases=("optimal control", "objective function", "decision rule"),
        neighbors=("math.DS", "eess.SY", "cs.RO"),
    ),
    Taxon(
        code="eess.SY",
        label="Systems and Control",
        description="Modeling, control, estimation, and validation of engineered systems.",
        terms=("system", "control", "signal", "feedback", "estimation", "validation"),
        phrases=("control system", "signal processing", "feedback system", "system identification"),
        neighbors=("math.DS", "math.OC", "cs.RO", "cs.NI"),
    ),
    Taxon(
        code="q-bio.NC",
        label="Neurons and Cognition",
        description="Neural, cognitive, behavioral, and computational neuroscience systems.",
        terms=("neural", "neuron", "cognitive", "brain", "attention", "behavior"),
        phrases=("neural system", "cognitive processing", "computational neuroscience"),
        neighbors=("cs.LG", "q-bio.QM"),
    ),
    Taxon(
        code="q-bio.QM",
        label="Quantitative Methods",
        description="Quantitative and computational methods for biological systems and evidence.",
        terms=("biological", "biology", "quantitative", "physiological", "population", "biomedical"),
        phrases=("biological system", "quantitative biology", "physiological model"),
        neighbors=("q-bio.NC", "math.ST"),
    ),
    Taxon(
        code="econ.EM",
        label="Econometrics",
        description="Statistical modeling, causal estimation, and validation for economic observations.",
        terms=("economic", "econometric", "causal", "panel", "market", "forecast"),
        phrases=("economic model", "causal inference", "time series"),
        neighbors=("math.ST", "stat.ML"),
    ),
)


FACET_DEFINITIONS = (
    FacetDefinition(
        "paper-type",
        "theoretical",
        "Theoretical research",
        "Develops or analyzes a formal theory, calculus, or mathematical framework.",
        ("theorem", "formal", "proof", "axiom", "calculus", "derivation"),
        ("theoretical framework", "formal model", "mathematical formulation"),
    ),
    FacetDefinition(
        "paper-type",
        "empirical",
        "Empirical research",
        "Evaluates claims using observed, measured, or experimentally generated evidence.",
        ("experiment", "empirical", "observed", "measured", "participants", "dataset"),
        ("empirical evaluation", "experimental results", "observational study"),
    ),
    FacetDefinition(
        "paper-type",
        "methodological",
        "Methodological research",
        "Introduces or evaluates a reusable method, algorithm, or analytical procedure.",
        ("method", "algorithm", "procedure", "pipeline", "approach", "technique"),
        ("proposed method", "new algorithm", "analytical procedure"),
    ),
    FacetDefinition(
        "paper-type",
        "review",
        "Review or synthesis",
        "Synthesizes, compares, or surveys an existing body of research.",
        ("review", "survey", "literature", "synthesis", "systematic"),
        ("literature review", "systematic review", "survey paper"),
    ),
    FacetDefinition(
        "paper-type",
        "systems",
        "Systems research",
        "Designs, implements, or evaluates an integrated software or engineered system.",
        ("system", "architecture", "implementation", "prototype", "runtime"),
        ("system architecture", "prototype implementation", "end-to-end system"),
    ),
    FacetDefinition(
        "contribution",
        "algorithm",
        "Algorithmic contribution",
        "Contributes an executable algorithm or update procedure.",
        ("algorithm", "procedure", "update", "pseudocode"),
        ("learning algorithm", "update rule"),
    ),
    FacetDefinition(
        "contribution",
        "framework",
        "Framework contribution",
        "Contributes an organizing formal, conceptual, or software framework.",
        ("framework", "architecture", "calculus", "model"),
        ("conceptual framework", "formal framework"),
    ),
    FacetDefinition(
        "contribution",
        "evaluation",
        "Evaluation contribution",
        "Contributes comparative measurements, validation results, or benchmark evidence.",
        ("evaluation", "benchmark", "results", "validation", "comparison"),
        ("comparative evaluation", "benchmark results"),
    ),
    FacetDefinition(
        "method",
        "recurrent-modeling",
        "Recurrent modeling",
        "Represents observations through state retained across an ordered sequence.",
        ("recurrent", "sequence", "hidden", "memory", "temporal"),
        ("recurrent neural network", "recurrent state"),
    ),
    FacetDefinition(
        "method",
        "lateral-propagation",
        "Lateral propagation",
        "Propagates local state or update signals across contextually related units.",
        ("lateral", "propagation", "diffusion", "neighbor"),
        ("lateral propagation", "lateral update"),
    ),
    FacetDefinition(
        "method",
        "uncertainty-modeling",
        "Uncertainty modeling",
        "Retains and evaluates uncertainty, evidence, validation, or confidence explicitly.",
        ("uncertainty", "evidence", "confidence", "validation", "indeterminate"),
        ("calculus of uncertainty", "uncertainty quantification"),
    ),
    FacetDefinition(
        "method",
        "predictive-validation",
        "Predictive validation",
        "Uses held-out or later observations to validate an earlier reconstructed state.",
        ("predictive", "forecast", "validation", "holdout", "rolling"),
        ("predictive validation", "rolling validation"),
    ),
    FacetDefinition(
        "method",
        "state-reconstruction",
        "State reconstruction",
        "Reconstructs an incomplete, latent, or evolving state from available evidence.",
        ("reconstruction", "state", "incomplete", "latent", "approximation"),
        ("state reconstruction", "equation reconstruction"),
    ),
    FacetDefinition(
        "evidence",
        "formal-derivation",
        "Formal derivation",
        "Supports the contribution through equations, proofs, or formal derivation.",
        ("equation", "proof", "derive", "derivation", "theorem"),
        ("formal derivation", "mathematical proof"),
    ),
    FacetDefinition(
        "evidence",
        "experimental-evaluation",
        "Experimental evaluation",
        "Supports the contribution through controlled experiments or measured trials.",
        ("experiment", "trial", "measurement", "result", "baseline"),
        ("experimental evaluation", "controlled experiment"),
    ),
    FacetDefinition(
        "evidence",
        "benchmark-evaluation",
        "Benchmark evaluation",
        "Reports performance using a benchmark, baseline, or comparative dataset.",
        ("benchmark", "baseline", "accuracy", "precision", "recall", "dataset"),
        ("benchmark dataset", "benchmark evaluation"),
    ),
    FacetDefinition(
        "artifact",
        "source-code",
        "Source code",
        "The paper describes or links an executable source-code artifact.",
        ("code", "implementation", "repository", "github", "gitlab"),
        ("source code", "code repository"),
    ),
    FacetDefinition(
        "artifact",
        "dataset",
        "Dataset",
        "The paper creates, uses, or links a structured research dataset.",
        ("dataset", "corpus", "data", "records"),
        ("research dataset", "data repository"),
    ),
)


TAXON_BY_CODE = {taxon.code: taxon for taxon in TAXA}

