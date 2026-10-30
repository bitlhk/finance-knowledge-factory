# Reproducing the isolated M1 service probe

Not a production installation. Requires Docker/Compose, approximately 10 GiB of
container memory limits plus CPU embedding/model memory and private disk caches.
The script acts only on Compose project `kf-m1-ragflow`; check name/port availability
before starting it. Do not reuse this project name for another user's work.

## Start and ingest

1. Prepare isolated Python environments. Core tests use `requirements-test.txt`.
   Service scripts additionally use requests and PyYAML from the document lock.
   Embedding uses `probes/documents/embedding.lock` in a separate Python 3.11 venv.
   Docling round-3 dependencies are in `docling-round3.lock`; Torch/torchvision
   `+cpu` wheels require the official `https://download.pytorch.org/whl/cpu` index.
   No system-wide Python installation is needed.
2. Prepare/pull/start storage, wait for its readiness, migrate, then start service:

```bash
python3 -m probes.documents.ragflow_service prepare
python3 -m probes.documents.ragflow_service pull
python3 -m probes.documents.ragflow_service dependencies
python3 -m probes.documents.ragflow_service migrate
python3 -m probes.documents.ragflow_service start
python3 -m probes.documents.ragflow_service status
```

Preparation creates private 0600 config and random **local test** credentials.
It does not copy a model/production key. Existing config is not overwritten.
Upstream admin bootstrap retains its built-in default account; keep both admin
and API on loopback. This is not a hardened production identity configuration.
Dependency image names are recorded in the script; resolved image digests from
the executed round are in `evidence/m1-round3/service/versions-and-isolation.json`.
Reproduction must compare those digests; upstream tags alone are not a supply-chain
lock. Do not recreate shared containers to resolve a Compose v1 compatibility issue.

3. Download the public FastEmbed model once into `.m1-local/embedding-model` using
   the isolated embedding environment (`TextEmbedding('BAAI/bge-small-zh-v1.5',
   cache_dir='.m1-local/embedding-model', threads=1)`). Compare the downloaded file
   hashes with `evidence/m1-round3/service/embedding-identity.json` before claiming
   the same model. Then start the bounded local embedding adapter in its own terminal:

```bash
.m1-local/embedding-venv/bin/python -m probes.documents.embedding_service
```

It binds the gateway address of this Docker project, not a public interface;
requests require the throwaway local password. It is not a general embedding
service and has no public reverse proxy. Ctrl-C stops it.

4. Register the two local accounts **once per fresh database**, then configure
   the embedding instance. Existing accounts use the same persisted local test
   config; do not interpret an account-already-exists response as a new registration.

```bash
python3 -m probes.documents.ragflow_client --register knowledge-m1@example.invalid
python3 -m probes.documents.ragflow_client --register knowledge-m1-other@example.invalid
python3 -m probes.documents.ragflow_client
python3 -m probes.documents.ingest_file evidence/m1-round3/sources/regulation.html --retrieval-fixture
python3 -m probes.documents.retrieve_service
python3 -m probes.documents.check_access
```

Each retrieval run prints its new evidence directory. Verify it offline with:
`python3 -m probes.documents.review_retrieval RUN_DIR --source evidence/m1-round3/sources/regulation.html`.
The review file is create-only. Do not overwrite prior runs to improve a score.

## Cross-format probes

`download_word` and `download_pdf` record the original bytes/hash/source URLs in
new directories. The PDF is a secondary reproduction, not authoritative activation.
Check hashes against retained receipts before claiming the same input. Pass the
printed original path to `ingest_file`; omit `--retrieval-fixture` so it does not
replace the HTML comparison dataset.

`parse_file` runs actual Docling, retaining dependency and conversion failures.
Use a private HF_HOME and a bounded execution timeout. PDF profile is born-digital,
CPU, two threads, no OCR or table-structure model. The full successful round needed
Docling's standard extras; HTML-only dependencies do not suffice for PDF.
Binary DOC also needs an isolated full Writer conversion environment, which has
not been validated in this round. Do not install it over a shared office service
or rename `.doc` to `.docx`.

`check_pdf_locations SOURCE_PDF INGESTION_REPORT` checks RAGFlow native positions;
add `--docling` with a Docling report for its native provenance. This only verifies
the saved coordinates/text and does not create a published Knowledge Core asset.

## Stop and preserve evidence

```bash
python3 -m probes.documents.ragflow_service stop
python3 -m probes.documents.ragflow_service status
```

Stop the separate embedding terminal with Ctrl-C as well. Volumes and `.m1-local`
evidence stay intact. No other Compose project or host service is stopped.
Never publish `compose.json`, `service.yaml`, `local-credentials.json`, HTTP headers,
or private `http-setup.json`. Export only the selected evidence after checking for
credentials. The recorded round's shutdown is in `service/stop-receipt.json`.
