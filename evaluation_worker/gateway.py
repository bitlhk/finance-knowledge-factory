"""Host-owned model gateway for the fixed evaluation flow."""
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from knowledge_core.contracts import digest


OPENJIUWEN_VERSION = "0.1.17.post1"


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ModelEnvironment:
    api_base: str
    model_name: str
    api_key: str

    @classmethod
    def from_env_file(cls, path):
        values = {}
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in {"FH_MODEL_URL", "FH_MODEL_NAME", "FH_MODEL_KEY"}:
                values[key] = value.strip().strip('"').strip("'")
        if any(not values.get(key) for key in
               ("FH_MODEL_URL", "FH_MODEL_NAME", "FH_MODEL_KEY")):
            raise ValueError("MODEL_ENVIRONMENT_INCOMPLETE")
        return cls(values["FH_MODEL_URL"], values["FH_MODEL_NAME"],
                   values["FH_MODEL_KEY"])


@dataclass(frozen=True)
class ModelDeployment:
    id: str
    provider: str
    endpoint_origin: str
    region: str
    execution_zone: str
    external: bool
    gateway_build_digest: str
    adapter_version: str
    qualification_digest: str

    def registration(self, environment):
        if environment.api_base.rstrip('/') != self.endpoint_origin.rstrip('/'):
            raise ValueError("MODEL_ENDPOINT_CONFIGURATION_MISMATCH")
        return {
            "id":self.id, "provider":self.provider,
            "modelRef":environment.model_name,
            "modelConfigDigest":model_config_digest(self.provider, environment),
            "endpointOrigin":self.endpoint_origin.rstrip('/'),
            "region":self.region, "executionZone":self.execution_zone,
            "external":self.external,
        }

    def runtime_identity(self, environment):
        return {**self.registration(environment),
                "gatewayBuildDigest":self.gateway_build_digest,
                "adapterVersion":self.adapter_version,
                "openJiuwenVersion":OPENJIUWEN_VERSION,
                "qualificationDigest":self.qualification_digest}


def model_config_digest(provider, environment):
    return digest({"provider":provider, "modelRef":environment.model_name,
                   "apiBase":environment.api_base.rstrip('/')})


def build_openjiuwen_model(environment):
    if version("openjiuwen") != OPENJIUWEN_VERSION:
        raise RuntimeError("OPENJIUWEN_VERSION_MISMATCH")
    from openjiuwen.core.common.logging.log_config import configure_log_config
    # Core owns the durable evaluation record. SDK prompt/answer logs would be
    # an ungoverned second archive, so the worker disables all SDK sinks.
    configure_log_config({
        "backend":"default", "level":"ERROR", "output":[],
        "interface_output":[], "performance_output":[],
    })
    from openjiuwen.core.foundation.llm import Model, ModelClientConfig, \
        ModelRequestConfig
    return Model(
        model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_key=environment.api_key,
            api_base=environment.api_base, timeout=120, max_retries=0,
            verify_ssl=True),
        model_config=ModelRequestConfig(
            model=environment.model_name, temperature=0, max_tokens=2048))


def _bounded_usage(metadata):
    if metadata is None:
        return {}
    values = metadata.model_dump() if hasattr(metadata, "model_dump") else metadata
    if not isinstance(values, dict):
        return {}
    mapping = {
        "input_tokens":"inputTokens", "output_tokens":"outputTokens",
        "total_tokens":"totalTokens", "cache_tokens":"cacheTokens",
        "reasoning_tokens":"reasoningTokens",
    }
    return {target:values[source] for source, target in mapping.items()
            if type(values.get(source)) is int and values[source] >= 0}


class CoreModelGatewayClient:
    """Core receipt interface fixed to a qualified gateway registration."""

    def __init__(self, core, actor, registration_digest, runtime_identity):
        self.__core = core
        self.__actor = actor
        self.__registration = registration_digest
        self.__runtime_identity = runtime_identity

    def prepare(self, authorization_digest, request_id, trace_id):
        return self.__core.prepare_model_invocation(
            self.__actor, self.__registration, authorization_digest,
            request_id, trace_id, self.__runtime_identity)

    def record(self, authorization_digest, attempt_digest, started_at,
               ended_at, outcome, response, provider_request_ref, usage):
        return self.__core.record_model_invocation(
            self.__actor, self.__registration, authorization_digest,
            attempt_digest, started_at, ended_at, outcome, response,
            provider_request_ref, usage)


class OpenJiuwenModelGateway:
    """Invokes only the Core-prepared request and records the actual attempt."""

    def __init__(self, core_client, environment,
                 model_factory=build_openjiuwen_model,
                 outbound_observer=None):
        self.__core_client = core_client
        self.__environment = environment
        self.__model = model_factory(environment)
        self.__outbound_observer = outbound_observer

    async def invoke(self, authorization_digest, request_id=None, trace_id=None):
        request_id = request_id or f"model-{uuid4().hex}"
        trace_id = trace_id or f"trace-{uuid4().hex}"
        prepared = self.__core_client.prepare(
            authorization_digest, request_id, trace_id)
        outbound = {"messages":prepared["messages"], "model":prepared["model"],
                    "temperature":prepared["temperature"]}
        if self.__outbound_observer:
            self.__outbound_observer(outbound)
        started = _now()
        attempt = prepared["invocationAttemptDigest"]
        try:
            response = await self.__model.invoke(
                prepared["messages"], model=prepared["model"], temperature=0,
                max_tokens=2048, timeout=120)
            answer = response.content
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("EVALUATION_MODEL_RESPONSE_INVALID")
            if len(answer) > prepared["maxAnswerCharacters"]:
                raise ValueError("EVALUATION_MODEL_RESPONSE_TOO_LARGE")
            usage = _bounded_usage(getattr(response, "usage_metadata", None))
            metadata = getattr(response, "metadata", {}) or {}
            provider_ref = str(metadata.get("request_id") or
                               f"unavailable:{request_id}")
            return self.__core_client.record(
                authorization_digest, attempt, started, _now(), "RETURNED",
                answer, provider_ref, usage)
        except Exception as error:
            self.__core_client.record(
                authorization_digest, attempt, started, _now(), "FAILED", None,
                f"unavailable:{request_id}",
                {"errorClass":type(error).__name__})
            raise
