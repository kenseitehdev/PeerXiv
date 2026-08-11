"""CoU-native lateral recurrent classifier for research papers.

This implementation is deliberately transparent.  It does not perform a
global backward pass.  Paper observations update a recurrent category state;
local prediction discrepancies are propagated laterally through the subject
graph, decayed, validation-gated, and retained through local eligibility
traces.  The resulting trajectories are evaluated through the Gamma and kappa
stages supplied by the PeerXiv CoU specification.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import exp, sqrt
import re
from typing import Any, Iterable, Mapping

from peerxiv.classifier import CoUClassification, CoUSnapshot

from .taxonomy import (
    FACET_DEFINITIONS,
    METADATA_SCHEMA_VERSION,
    TAXA,
    TAXONOMY_VERSION,
    FacetDefinition,
    Taxon,
)


TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9'-]{1,}")
SPACE_PATTERN = re.compile(r"\s+")
STOPWORDS = {
    "about",
    "after",
    "also",
    "among",
    "and",
    "are",
    "been",
    "before",
    "being",
    "between",
    "both",
    "can",
    "from",
    "have",
    "into",
    "its",
    "may",
    "more",
    "most",
    "not",
    "our",
    "paper",
    "results",
    "shows",
    "that",
    "the",
    "their",
    "these",
    "this",
    "through",
    "using",
    "was",
    "were",
    "which",
    "with",
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    exponential = exp(value)
    return exponential / (1.0 + exponential)


def _normalize_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", value.casefold()).strip()


def _tokens(value: str) -> list[str]:
    return TOKEN_PATTERN.findall(value.casefold())


def _state_label(value: float) -> str:
    if value >= 0.70:
        return "true"
    if value >= 0.36:
        return "almost-true"
    if value >= 0.18:
        return "undetermined"
    if value >= 0.07:
        return "almost-false"
    return "false"


@dataclass(frozen=True, slots=True)
class Observation:
    index: int
    kind: str
    label: str
    text: str
    weight: float

    def to_evidence(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "label": self.label,
            "token_count": len(_tokens(self.text)),
        }


class CoUPaperClassifierBackend:
    """Hierarchical paper classifier using CoU-gated lateral propagation."""

    version = "cou-paper-lateral-0.1.0"
    decision_threshold = 0.36
    retention = 0.68
    eligibility_decay = 0.62
    lateral_decay = 0.46
    lateral_rounds = 2
    local_learning_rate = 0.16
    forecast_horizon = 3

    def classify(self, snapshot: CoUSnapshot) -> CoUClassification:
        document = snapshot.state.get("document")
        if not isinstance(document, Mapping):
            raise ValueError("A paper classification snapshot requires state.document")

        observations = self._observations(document)
        if not observations:
            raise ValueError("The paper must contain a title, abstract, keywords, or section text")

        category_results, observation_trace = self._run_recurrent_network(observations)
        ranked = sorted(category_results.values(), key=lambda item: item["evaluation"], reverse=True)
        primary = ranked[0]
        accepted = [item for item in ranked if item["evaluation"] >= self.decision_threshold]
        label = primary["code"] if primary["evaluation"] >= 0.20 else "unclassified"
        metadata = self._descriptive_metadata(document, observations, ranked)

        final_mu = {
            "primary_category": label,
            "accepted_categories": [item["code"] for item in accepted],
            "category_states": {
                item["code"]: {
                    "value": item["evaluation"],
                    "label": item["state_label"],
                }
                for item in ranked
            },
        }
        delta_mu = {
            item["code"]: item["movement"]
            for item in ranked
            if abs(item["movement"]) >= 0.000001
        }

        components = {
            "algorithm": {
                "kind": "cou-lateral-recurrent-paper-classifier",
                "version": self.version,
                "learning": "local-eligibility-and-lateral-propagation",
                "global_backpropagation": False,
                "taxonomy_version": TAXONOMY_VERSION,
                "metadata_schema_version": METADATA_SCHEMA_VERSION,
                "parameters": {
                    "retention": self.retention,
                    "eligibility_decay": self.eligibility_decay,
                    "lateral_decay": self.lateral_decay,
                    "lateral_rounds": self.lateral_rounds,
                    "local_learning_rate": self.local_learning_rate,
                    "decision_threshold": self.decision_threshold,
                },
            },
            "gamma": {
                item["code"]: item["gamma"]
                for item in ranked
            },
            "kappa": {
                "candidate_equation_reconstruction": {
                    item["code"]: item["reconstruction"] for item in ranked
                },
                "candidate_predictive_propagation": {
                    item["code"]: item["forecast"] for item in ranked
                },
                "equation_state_classification": {
                    item["code"]: item["state_label"] for item in ranked
                },
                "structural_validity": {
                    item["code"]: item["structural_validation"] for item in ranked
                },
                "predictive_validation": {
                    item["code"]: item["predictive_validation"] for item in ranked
                },
            },
            "mu": final_mu,
            "delta_mu": delta_mu,
            "propagation": {
                item["code"]: item["forecast"] for item in ranked[:5]
            },
            "categories": ranked,
            "descriptive_metadata": metadata,
        }

        kappa_trace = (
            {
                "step": "candidate-equation-reconstruction",
                "operator": "R",
                "retained": True,
                "candidate_count": len(ranked),
            },
            {
                "step": "predictive-propagation",
                "operator": "Pi",
                "retained": True,
                "horizon": self.forecast_horizon,
            },
            {
                "step": "equation-state-classification",
                "operator": "C",
                "retained": True,
                "primary": label,
            },
            {
                "step": "structural-validity-isolation",
                "operator": "V_struct",
                "retained": primary["structural_validation"] >= 0.30,
                "value": primary["structural_validation"],
            },
            {
                "step": "predictive-validation",
                "operator": "V_pred",
                "retained": primary["predictive_validation"] >= 0.45,
                "value": primary["predictive_validation"],
            },
            {
                "step": "evaluation",
                "operator": "Eval",
                "retained": label != "unclassified",
                "threshold": self.decision_threshold,
                "value": primary["evaluation"],
            },
        )

        return CoUClassification.create(
            classifier_version=self.version,
            snapshot=snapshot,
            label=label,
            components=components,
            trace=tuple(observation_trace) + kappa_trace,
        )

    def _observations(self, document: Mapping[str, Any]) -> list[Observation]:
        observations: list[Observation] = []

        def append(kind: str, label: str, value: Any, weight: float) -> None:
            text = str(value or "").strip()
            if text:
                observations.append(Observation(len(observations), kind, label, text, weight))

        append("title", "Title", document.get("title"), 2.8)
        keywords = document.get("keywords") or []
        if isinstance(keywords, Iterable) and not isinstance(keywords, (str, bytes, Mapping)):
            append("keywords", "Author keywords", "; ".join(str(item) for item in keywords), 2.4)
        append("abstract", "Abstract", document.get("abstract"), 1.65)

        sections = document.get("sections") or []
        if isinstance(sections, Iterable) and not isinstance(sections, (str, bytes, Mapping)):
            for position, section in enumerate(sections, start=1):
                if isinstance(section, Mapping):
                    heading = str(section.get("heading") or f"Section {position}").strip()
                    text = section.get("text")
                else:
                    heading = f"Section {position}"
                    text = section
                append("section", heading, text, 1.0)
        return observations

    def _run_recurrent_network(
        self,
        observations: list[Observation],
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        hidden = {taxon.code: 0.0 for taxon in TAXA}
        eligibility = {taxon.code: 0.0 for taxon in TAXA}
        histories = {taxon.code: [] for taxon in TAXA}
        direct_histories = {taxon.code: [] for taxon in TAXA}
        error_histories = {taxon.code: [] for taxon in TAXA}
        observation_trace: list[dict[str, Any]] = []

        for observation in observations:
            direct = {taxon.code: self._taxon_evidence(observation, taxon) for taxon in TAXA}
            prediction = {code: self.retention * value for code, value in hidden.items()}
            local_error = {code: direct[code] - prediction[code] for code in hidden}
            movement = sum(abs(value) for value in local_error.values()) / max(len(local_error), 1)
            token_coverage = _clamp(len(_tokens(observation.text)) / 60.0)
            tau_gate = _clamp(0.15 + (movement * 2.8))
            validation_gate = _clamp(0.30 + (0.70 * token_coverage))
            propagation_gate = tau_gate * validation_gate
            lateral, round_trace = self._propagate_laterally(local_error, propagation_gate)

            for taxon in TAXA:
                code = taxon.code
                eligibility[code] = (
                    self.eligibility_decay * eligibility[code]
                    + abs(direct[code])
                )
                local_plasticity = (
                    self.local_learning_rate
                    * lateral[code]
                    * _clamp(eligibility[code])
                )
                hidden[code] = _clamp(
                    self.retention * hidden[code]
                    + (1.0 - self.retention) * direct[code]
                    + lateral[code]
                    + local_plasticity
                )
                histories[code].append(hidden[code])
                direct_histories[code].append(direct[code])
                error_histories[code].append(local_error[code])

            top_direct = sorted(direct.items(), key=lambda item: abs(item[1]), reverse=True)[:4]
            top_lateral = sorted(lateral.items(), key=lambda item: abs(item[1]), reverse=True)[:4]
            top_eligibility = sorted(
                eligibility.items(), key=lambda item: abs(item[1]), reverse=True
            )[:4]
            top_state = sorted(hidden.items(), key=lambda item: abs(item[1]), reverse=True)[:4]
            observation_trace.append(
                {
                    "step": "lateral-recurrent-update",
                    "observation": observation.to_evidence(),
                    "tau_delta_mu": _round(tau_gate),
                    "validation_gate": _round(validation_gate),
                    "propagation_gate": _round(propagation_gate),
                    "local_error_magnitude": _round(movement),
                    "direct_evidence": {code: _round(value) for code, value in top_direct if value},
                    "lateral_propagation": {code: _round(value) for code, value in top_lateral if value},
                    "eligibility_trace": {
                        code: _round(value) for code, value in top_eligibility if value
                    },
                    "recurrent_state": {code: _round(value) for code, value in top_state if value},
                    "rounds": round_trace,
                    "retained": True,
                }
            )

        results: dict[str, dict[str, Any]] = {}
        for taxon in TAXA:
            code = taxon.code
            gamma = self._gamma(histories[code])
            structural = self._structural_validation(direct_histories[code], observations)
            predictive = 1.0 - (
                sum(abs(value) for value in error_histories[code])
                / max(len(error_histories[code]), 1)
            )
            predictive = _clamp(predictive)
            accumulated_state = 0.60 * gamma["logistic"] + 0.40 * gamma["rectangular"]
            evaluation = _clamp(
                accumulated_state
                * (0.70 + 0.30 * structural)
                * (0.70 + 0.30 * predictive)
            )
            movement = histories[code][-1] - histories[code][-2] if len(histories[code]) > 1 else histories[code][-1]
            trend = movement
            forecast = [
                _round(_clamp(histories[code][-1] + trend * horizon))
                for horizon in range(1, self.forecast_horizon + 1)
            ]
            results[code] = {
                "code": code,
                "label": taxon.label,
                "description": taxon.description,
                "evaluation": _round(evaluation),
                "state_label": _state_label(evaluation),
                "accepted": evaluation >= self.decision_threshold,
                "structural_validation": _round(structural),
                "predictive_validation": _round(predictive),
                "movement": _round(movement),
                "gamma": gamma,
                "reconstruction": [_round(value) for value in histories[code]],
                "forecast": forecast,
            }
        return results, observation_trace

    def _taxon_evidence(self, observation: Observation, taxon: Taxon) -> float:
        normalized = _normalize_text(observation.text)
        token_counts = Counter(_tokens(normalized))
        term_hits = sum(token_counts[term] for term in taxon.terms)
        phrase_hits = sum(normalized.count(phrase) for phrase in taxon.phrases)
        if not term_hits and not phrase_hits:
            return 0.0
        denominator = sqrt(max(len(token_counts), 10))
        raw = observation.weight * (term_hits + 2.4 * phrase_hits) / denominator
        return _clamp(1.0 - exp(-0.72 * raw))

    def _propagate_laterally(
        self,
        local_error: Mapping[str, float],
        gate: float,
    ) -> tuple[dict[str, float], list[dict[str, Any]]]:
        signal = dict(local_error)
        accumulated = {taxon.code: 0.0 for taxon in TAXA}
        trace: list[dict[str, Any]] = []
        taxon_by_code = {taxon.code: taxon for taxon in TAXA}

        for round_index in range(1, self.lateral_rounds + 1):
            next_signal: dict[str, float] = {}
            decay = self.lateral_decay**round_index
            for taxon in TAXA:
                neighbor_values = [signal[code] for code in taxon.neighbors if code in signal]
                neighbor_mean = sum(neighbor_values) / len(neighbor_values) if neighbor_values else 0.0
                propagated = gate * decay * neighbor_mean
                next_signal[taxon.code] = propagated
                accumulated[taxon.code] += propagated
            signal = next_signal
            leading = sorted(signal.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
            trace.append(
                {
                    "round": round_index,
                    "decay": _round(decay),
                    "leading_signals": {
                        code: _round(value)
                        for code, value in leading
                        if code in taxon_by_code and value
                    },
                }
            )
        return accumulated, trace

    def _gamma(self, values: list[float]) -> dict[str, float]:
        rectangular = sum(values) / len(values)
        if len(values) == 1:
            trapezoidal = midpoint = extrapolated = values[0]
        else:
            trapezoidal = sum(
                (left + right) / 2.0 for left, right in zip(values, values[1:])
            ) / (len(values) - 1)
            midpoint_values = [
                (left + 2.0 * right) / 3.0
                for left, right in zip(values, values[1:])
            ]
            midpoint = sum(midpoint_values) / len(midpoint_values)
            extrapolated = _clamp(values[-1] + (values[-1] - values[-2]))
        contrast = 2.0 * extrapolated - midpoint
        logistic = _sigmoid(6.0 * (contrast - 0.30))
        return {
            "rectangular": _round(rectangular),
            "trapezoidal": _round(trapezoidal),
            "midpoint": _round(midpoint),
            "first_order_extrapolation": _round(extrapolated),
            "contrast": _round(contrast),
            "logistic": _round(logistic),
        }

    def _structural_validation(
        self,
        values: list[float],
        observations: list[Observation],
    ) -> float:
        supported = [index for index, value in enumerate(values) if value >= 0.10]
        if not supported:
            return 0.0
        kinds = {observations[index].kind for index in supported}
        breadth = len(supported) / len(observations)
        title_or_keywords = bool({"title", "keywords"} & kinds)
        abstract = "abstract" in kinds
        section = "section" in kinds
        structural_coverage = (
            0.25 * float(title_or_keywords)
            + 0.35 * float(abstract)
            + 0.40 * float(section or len(observations) <= 3)
        )
        return _clamp(0.55 * structural_coverage + 0.45 * breadth)

    def _descriptive_metadata(
        self,
        document: Mapping[str, Any],
        observations: list[Observation],
        ranked: list[dict[str, Any]],
    ) -> dict[str, Any]:
        subject_tags = [
            {
                "facet": "subject",
                "namespace": "peerxiv.subject",
                "slug": item["code"].casefold(),
                "label": item["label"],
                "description": item["description"],
                "state": item["state_label"],
                "weight": item["evaluation"],
                "evidence": self._taxon_evidence_spans(observations, item["code"]),
                "provenance": "cou-category-state",
            }
            for item in ranked[:5]
            if item["evaluation"] >= 0.15
        ]

        facet_tags = []
        for definition in FACET_DEFINITIONS:
            weight, evidence = self._facet_evidence(observations, definition)
            if weight < 0.16:
                continue
            facet_tags.append(
                {
                    "facet": definition.facet,
                    "namespace": f"peerxiv.{definition.facet}",
                    "slug": definition.slug,
                    "label": definition.label,
                    "description": definition.description,
                    "state": _state_label(weight),
                    "weight": _round(weight),
                    "evidence": evidence,
                    "provenance": "cou-faceted-extraction",
                }
            )

        concept_tags = self._concept_tags(document, observations)
        tags = subject_tags + sorted(
            facet_tags,
            key=lambda item: (item["facet"], -item["weight"], item["label"]),
        ) + concept_tags
        primary = ranked[0]
        prominent_facets = [tag["label"] for tag in facet_tags if tag["weight"] >= 0.34][:4]
        descriptor = ", ".join(prominent_facets)
        summary = f"{primary['label']} research"
        if descriptor:
            summary += f" characterized by {descriptor}"
        summary += "."

        return {
            "schema_version": METADATA_SCHEMA_VERSION,
            "taxonomy_version": TAXONOMY_VERSION,
            "classifier_version": self.version,
            "summary": summary,
            "primary_subject": {
                "code": primary["code"],
                "label": primary["label"],
                "state": primary["state_label"],
                "weight": primary["evaluation"],
            },
            "tags": tags,
        }

    def _taxon_evidence_spans(
        self,
        observations: list[Observation],
        code: str,
    ) -> list[dict[str, Any]]:
        taxon = next(item for item in TAXA if item.code == code)
        evidence = []
        for observation in observations:
            normalized = _normalize_text(observation.text)
            matched = [phrase for phrase in taxon.phrases if phrase in normalized]
            matched.extend(term for term in taxon.terms if term in set(_tokens(normalized)))
            if matched:
                evidence.append(self._evidence_span(observation, matched[:4]))
        return evidence[:4]

    def _facet_evidence(
        self,
        observations: list[Observation],
        definition: FacetDefinition,
    ) -> tuple[float, list[dict[str, Any]]]:
        raw = 0.0
        evidence = []
        for observation in observations:
            normalized = _normalize_text(observation.text)
            token_set = set(_tokens(normalized))
            phrases = [phrase for phrase in definition.phrases if phrase in normalized]
            terms = [term for term in definition.terms if term in token_set]
            if not phrases and not terms:
                continue
            local = observation.weight * (len(terms) + 2.2 * len(phrases))
            raw += local / sqrt(max(len(token_set), 12))
            evidence.append(self._evidence_span(observation, (phrases + terms)[:4]))
        return _clamp(1.0 - exp(-0.55 * raw)), evidence[:4]

    def _evidence_span(
        self,
        observation: Observation,
        matched: Iterable[str],
    ) -> dict[str, Any]:
        matched_terms = list(dict.fromkeys(matched))
        normalized = SPACE_PATTERN.sub(" ", observation.text).strip()
        lower = normalized.casefold()
        first_position = min(
            (lower.find(term.casefold()) for term in matched_terms if lower.find(term.casefold()) >= 0),
            default=0,
        )
        start = max(0, first_position - 70)
        end = min(len(normalized), first_position + 170)
        excerpt = normalized[start:end]
        if start:
            excerpt = f"…{excerpt}"
        if end < len(normalized):
            excerpt = f"{excerpt}…"
        return {
            "observation": observation.index,
            "location": observation.label,
            "matched": matched_terms,
            "excerpt": excerpt,
        }

    def _concept_tags(
        self,
        document: Mapping[str, Any],
        observations: list[Observation],
    ) -> list[dict[str, Any]]:
        author_keywords = [
            str(value).strip()
            for value in document.get("keywords") or []
            if str(value).strip()
        ]
        tags: list[dict[str, Any]] = []
        seen: set[str] = set()
        for keyword in author_keywords[:12]:
            slug = re.sub(r"[^a-z0-9]+", "-", keyword.casefold()).strip("-")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            tags.append(
                {
                    "facet": "concept",
                    "namespace": "peerxiv.concept",
                    "slug": slug,
                    "label": keyword,
                    "description": "Author-supplied concept associated with this paper.",
                    "state": "true",
                    "weight": 1.0,
                    "evidence": [{"location": "Author keywords", "matched": [keyword]}],
                    "provenance": "author-supplied",
                }
            )

        counter: Counter[str] = Counter()
        locations: dict[str, str] = {}
        for observation in observations:
            words = [word for word in _tokens(observation.text) if word not in STOPWORDS and len(word) > 2]
            for size in (2, 3):
                for index in range(len(words) - size + 1):
                    phrase = " ".join(words[index : index + size])
                    counter[phrase] += 1
                    locations.setdefault(phrase, observation.label)
        for phrase, count in counter.most_common(20):
            if len(tags) >= 18:
                break
            slug = phrase.replace(" ", "-")
            if slug in seen or (count < 2 and len(observations) > 2):
                continue
            seen.add(slug)
            weight = _clamp(0.28 + 0.14 * count)
            tags.append(
                {
                    "facet": "concept",
                    "namespace": "peerxiv.concept",
                    "slug": slug,
                    "label": phrase,
                    "description": "Recurring descriptive concept extracted from the paper text.",
                    "state": _state_label(weight),
                    "weight": _round(weight),
                    "evidence": [{"location": locations[phrase], "matched": [phrase]}],
                    "provenance": "cou-concept-extraction",
                }
            )
        return tags
