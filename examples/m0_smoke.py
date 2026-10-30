"""Repeatable synthetic M0 walkthrough; never calls a model or remote service."""

import json
import tempfile
from pathlib import Path

from knowledge_core.contracts import Rejected, text_digest
from knowledge_core.core import Core
from tests.support import AUTHOR, READER, consume, policy, publish, source


def run():
    with tempfile.TemporaryDirectory(prefix="knowledge-m0-") as directory:
        database = Path(directory) / "m0.sqlite"
        core = Core(database)
        core.set_policy(AUTHOR, policy(), 0)
        credit = publish(core)
        faq = publish(core, "faq")
        original = consume(core)
        faq_result = consume(core, "faq")
        draft = {**credit["recipe"], "revision": 2, "intendedConsumers": ["different-user"]}
        core.save_recipe(AUTHOR, draft, 1)
        after_draft = consume(core)
        assert after_draft["manifestDigest"] == original["manifestDigest"]
        assert after_draft["result"] == original["result"]
        upload = source(revision=2)
        upload["content"] += "\nNew upload: not yet authoritative."
        upload["contentDigest"] = text_digest(upload["content"])
        upload_sha = core.register_source(AUTHOR, upload)
        after_registration = consume(core)
        assert after_registration["result"] == original["result"]
        core.activate_source(AUTHOR, upload_sha, "2026-11-01")
        try:
            consume(core)
            raise AssertionError("Old knowledge was not blocked")
        except Rejected as exc:
            activation_denial = exc.code
            assert activation_denial == "SOURCE_SUPERSEDED_OR_REVOKED"
        core.close()
        core = Core(database)
        replay = core.replay(READER, original["receiptDigest"])
        assert replay["result"] == original["result"] and core.execution_count == 0
        core.set_policy(AUTHOR, policy(2, source_reader=False), 1)
        try:
            consume(core, "faq")
            raise AssertionError("Source access revocation was not enforced")
        except Rejected as exc:
            authorization_denial = exc.code
            assert authorization_denial == "FORBIDDEN"
        objects = [{"digest": sha, "kind": kind, "body": json.loads(body)}
                   for sha, kind, body in core.db.execute("SELECT digest,kind,body FROM objects ORDER BY kind,digest")]
        report = {"mode": "M0_REFERENCE_ONLY", "remoteCalls": 0, "realIAMVerified": False,
                  "realHarnessInstalled": False, "flowableExecuted": False,
                  "credit": {"manifestDigest": credit["manifest"], "bindingDigest": credit["binding"], "receipt": original},
                  "faq": {"manifestDigest": faq["manifest"], "bindingDigest": faq["binding"], "receipt": faq_result},
                  "checks": {"draftDidNotChangePublishedService": True,
                             "registrationDidNotActivateSource": True,
                             "activationOfReplacementBlockedOldSource": activation_denial,
                             "currentSourceRevocationDeniedFAQ": authorization_denial,
                             "restartReplayMatchedOriginal": replay["result"] == original["result"],
                             "executionsAfterRestartReplay": core.execution_count},
                  "objects": objects}
        core.close()
        return report


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "evidence/m0-walkthrough.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(run(), ensure_ascii=False, indent=2) + "\n")
    print(str(target))
