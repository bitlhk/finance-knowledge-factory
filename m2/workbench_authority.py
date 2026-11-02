"""Trusted workbench identity boundary.

The browser supplies only an opaque authenticated session. A server-owned
resolver establishes the principal, authority, and roles. Request bodies never
select an actor or grant a privilege.
"""
from dataclasses import dataclass

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor
from m2.synthetic_context import AUTHOR, CONTEXT, READER, REVIEWER, SCOPE


OPERATIONS = {
    "candidate.produce": ("operator", frozenset()),
    "evaluation.start": ("operator", frozenset()),
    "source.activate": ("source-authority", frozenset({"source.activate"})),
    "document.approve": ("reviewer", frozenset({"document.approve"})),
    "manifest.publish": ("publisher", frozenset({"manifest.publish", "binding.manage"})),
}


@dataclass(frozen=True)
class WorkbenchAuthorities:
    producer: Actor
    reader: Actor
    context: object
    scope: dict
    resolver: object | None = None
    isolated: bool = False
    require_separation: bool = True

    @classmethod
    def synthetic(cls):
        return cls(AUTHOR, READER, CONTEXT, SCOPE, isolated=True,
                   require_separation=False)

    def __post_init__(self):
        if self.isolated:
            return
        if self.resolver is None:
            raise ValueError("WORKBENCH_AUTHENTICATOR_REQUIRED")
        identities = (self.producer.principal, self.reader.principal,
                      self.producer.authority, self.reader.authority)
        if any("synthetic" in value.casefold() for value in identities):
            raise ValueError("SYNTHETIC_IDENTITY_FORBIDDEN")

    def authenticate(self, operation, headers=None):
        if operation not in OPERATIONS:
            raise Rejected("WORKBENCH_OPERATION_FORBIDDEN")
        if self.isolated:
            if operation == "document.approve":
                return REVIEWER
            return AUTHOR
        identity = self.resolver(headers)
        if (not isinstance(identity, dict)
                or set(identity) != {"principal", "authority", "roles"}
                or not isinstance(identity["principal"], str)
                or not isinstance(identity["authority"], str)
                or not isinstance(identity["roles"], (set, frozenset))):
            raise Rejected("WORKBENCH_AUTHENTICATION_REQUIRED")
        role, privileges = OPERATIONS[operation]
        if role not in identity["roles"]:
            raise Rejected("WORKBENCH_AUTHORIZATION_REJECTED")
        if ("synthetic" in identity["principal"].casefold()
                or "synthetic" in identity["authority"].casefold()):
            raise Rejected("SYNTHETIC_IDENTITY_FORBIDDEN")
        return Actor(self.producer.tenant, identity["principal"],
                     identity["authority"], privileges)

    def check_separation(self, operator_ref, reviewer):
        if (self.require_separation and operator_ref
                and (reviewer.principal == operator_ref.get("principal")
                     or reviewer.authority == operator_ref.get("authority"))):
            raise Rejected("REVIEWER_SEPARATION_REQUIRED")

    @staticmethod
    def audit(actor):
        return {"principal":actor.principal, "authority":actor.authority}
