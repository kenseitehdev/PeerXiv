from peerxiv.classifier import CoUClassification, CoUClassifier, CoUSnapshot


class ExampleCoUBackend:
    version = "cou-test-1"

    def classify(self, snapshot):
        return CoUClassification.create(
            classifier_version=self.version,
            snapshot=snapshot,
            label="undetermined",
            components={"state": snapshot.state, "validation": snapshot.validation},
            trace=({"step": "test-only", "retained": True},),
        )


def test_cou_classifier_retains_subject_and_version():
    classifier = CoUClassifier()
    classifier.register(ExampleCoUBackend())
    snapshot = CoUSnapshot(
        subject_type="paper_version",
        subject_id="version-1",
        subject_version="v1",
        state={"p": 0.5, "s": 0.0},
        evidence=({"source": "fixture"},),
        validation=({"rule": "fixture-validation"},),
        context={"workspace": "test"},
    )

    result = classifier.classify(snapshot)
    assert result.classifier_version == "cou-test-1"
    assert result.subject_id == "version-1"
    assert result.subject_version == "v1"
    assert result.components["state"] == {"p": 0.5, "s": 0.0}
    assert result.trace[0]["retained"] is True
