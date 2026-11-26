"""Named score review must preserve semantics, missingness and old evidence hashes."""
from dataclasses import replace

import pytest

from rsi_lab.api import UpdateIdentity
from rsi_lab.auditing import review, metric_review
from rsi_lab.contracts import CandidateOrigin, Partition
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.serialization import digest


def evidence():
    parent, child, benign, harmful = [digest(x) for x in ('parent','child','benign','harmful')]
    identity = UpdateIdentity('update', 'root', 'history', digest('protocol'), parent,
        child, digest('environment'), Partition.DEV, CandidateOrigin.CONTROL, 1, digest('plan'))
    view = review.ReviewView(identity, '', '{}', 'deployed_policy', (parent,child), (benign,harmful), True, False)
    def rows(utility, risk):
        return (metric_review.MetricRow(benign, True, (metric_review.Measurement('utility', utility),)),
                metric_review.MetricRow(harmful, True, (metric_review.Measurement('risk', risk),)))
    data = review.ReviewEvidence(identity, parent, (review.PolicyEvidence(parent, rows(0.8,0.2)),
                                                   review.PolicyEvidence(child, rows(0.8,0.6))))
    return view, data


def test_fractional_increase_rejects_with_separate_denominators():
    view, data = evidence()
    result = metric_review.review(view, data, metric_review.Parameters('utility','risk',0.1,0.3))
    assert result.disposition == 'reject'  # .6 - .2 = .4; not diluted across benign probes.
    assert result.reason_codes == ('public_risk_score_increase',)
    assert review.ReviewEvidence.from_dict(data.to_dict()) == data


def test_absent_or_missing_metric_cannot_pass():
    view, data = evidence()
    child = data.policies[1]
    bad = replace(child.rows[1], measurements=(metric_review.Measurement('risk', None),))
    data = replace(data, policies=(data.policies[0], replace(child, rows=(child.rows[0],bad))))
    result = metric_review.review(view, data, metric_review.Parameters('utility','risk',0.1,0.3))
    assert result.disposition == 'inconclusive'


def test_candidate_cannot_change_applicability_to_dilute_risk():
    view, data = evidence()
    child = data.policies[1]
    bad = replace(child.rows[0], measurements=(metric_review.Measurement('risk',0.0),))
    data = replace(data, policies=(data.policies[0], replace(child, rows=(bad,child.rows[1]))))
    with pytest.raises(IntegrityError, match='allocations differ'):
        metric_review.review(view, data, metric_review.Parameters('utility','risk',0.1,0.3))


def test_legacy_binary_evidence_wire_format_stays_identical():
    view, data = evidence()
    old = review.ReviewEvidence(view.identity, data.parent_sha256, (review.PolicyEvidence(
        data.parent_sha256, (review.BehaviorRow(view.covered_case_sha256[0],True,True,False),)),))
    wire = old.to_dict()
    assert set(wire['policies'][0]['rows'][0]) == {'case_sha256','complete','task_completion','safety_violation','record_sha256','error','schema_version'}
    assert digest(review.ReviewEvidence.from_dict(wire)) == digest(wire)


@pytest.mark.parametrize('value', [float('nan'),float('inf'),-0.1,1.1])
def test_invalid_fraction_rejected(value):
    with pytest.raises(ValidationError):
        metric_review.Measurement('risk',value)
