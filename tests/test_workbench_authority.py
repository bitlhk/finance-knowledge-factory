import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor
from m2.synthetic_context import AUTHOR, CONTEXT, SCOPE
from m2.workbench_authority import WorkbenchAuthorities


def authorities():
    identities = {
        "operator": {"principal":"business-operator", "authority":"iam/operator",
                     "roles":{"operator"}},
        "same-reviewer": {"principal":"business-operator", "authority":"iam/operator",
                          "roles":{"reviewer"}},
        "reviewer": {"principal":"release-reviewer", "authority":"iam/reviewer",
                     "roles":{"reviewer"}},
        "source": {"principal":"source-owner", "authority":"iam/source-owner",
                   "roles":{"source-authority"}},
        "publisher": {"principal":"release-publisher", "authority":"iam/publisher",
                      "roles":{"publisher"}},
    }

    def resolve(headers):
        return identities.get((headers or {}).get("Session"))

    producer = Actor("m2-isolated", "trusted-producer", "iam/producer",
                     AUTHOR.privileges)
    reader = Actor("m2-isolated", "trusted-reader", "iam/reader")
    return WorkbenchAuthorities(producer, reader, CONTEXT, SCOPE,
                                resolver=resolve, isolated=False)


def test_formal_identity_is_server_resolved_and_roles_are_minimal():
    boundary = authorities()
    operator = boundary.authenticate("candidate.produce", {"Session":"operator"})
    assert operator.principal == "business-operator"
    assert operator.privileges == frozenset()
    reviewer = boundary.authenticate("document.approve", {"Session":"reviewer"})
    assert reviewer.privileges == frozenset({"document.approve"})
    publisher = boundary.authenticate("manifest.publish", {"Session":"publisher"})
    assert publisher.privileges == frozenset({"manifest.publish", "binding.manage"})
    with pytest.raises(Rejected, match="WORKBENCH_AUTHENTICATION_REQUIRED"):
        boundary.authenticate("candidate.produce", {})
    with pytest.raises(Rejected, match="WORKBENCH_AUTHORIZATION_REJECTED"):
        boundary.authenticate("document.approve", {"Session":"operator"})


def test_formal_mode_rejects_synthetic_identity_and_enforces_separation():
    with pytest.raises(ValueError, match="SYNTHETIC_IDENTITY_FORBIDDEN"):
        WorkbenchAuthorities(AUTHOR, Actor("m2-isolated", "reader", "iam/reader"),
                             CONTEXT, SCOPE, resolver=lambda _: {})
    boundary = authorities()
    operator = boundary.authenticate("candidate.produce", {"Session":"operator"})
    same = boundary.authenticate("document.approve", {"Session":"same-reviewer"})
    with pytest.raises(Rejected, match="REVIEWER_SEPARATION_REQUIRED"):
        boundary.check_separation(boundary.audit(operator), same)
    independent = boundary.authenticate("document.approve", {"Session":"reviewer"})
    boundary.check_separation(boundary.audit(operator), independent)


def test_source_activation_and_release_are_distinct_authorities():
    boundary = authorities()
    source = boundary.authenticate("source.activate", {"Session":"source"})
    reviewer = boundary.authenticate("document.approve", {"Session":"reviewer"})
    assert source.privileges == frozenset({"source.activate"})
    assert reviewer.privileges == frozenset({"document.approve"})
    with pytest.raises(Rejected, match="WORKBENCH_AUTHORIZATION_REJECTED"):
        boundary.authenticate("source.activate", {"Session":"reviewer"})
    with pytest.raises(Rejected, match="WORKBENCH_AUTHORIZATION_REJECTED"):
        boundary.authenticate("manifest.publish", {"Session":"source"})
