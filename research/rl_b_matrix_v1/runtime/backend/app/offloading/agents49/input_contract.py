"""Versioned, checkpoint-bound preprocessing. No model or simulator changes."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path

import numpy as np

from .normalizer import FEATURE_NAMES, SCALES, BINARY_INDICES, CONTRACT_VERSION, normalize

INPUT_VERSION = "agents49-input-v1"
MODEL_VERSION = "agents49-model-contract-v1"
INDEX_VERSION = "agents49-contract-index-v1"
ACTIONS = ("local", "edge", "cloud")
WEIGHT_SHAPES = ((49, 64), (64,), (64, 64), (64,), (64, 3), (3,))


class InputContractError(ValueError):
    pass


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise InputContractError("Invalid SHA-256")
    return value


def normalizer_spec():
    return dict(version=CONTRACT_VERSION, scales=SCALES.tolist(),
                binary_indices=list(BINARY_INDICES), transform="log1p(x/scale)", dtype="float64")


@dataclass(frozen=True)
class InputSpec:
    feature_mode: str = "full"
    zeroed_feature_indices: tuple = ()

    def __post_init__(self):
        dropped = self.zeroed_feature_indices
        if type(dropped) is not tuple or any(type(i) is not int or not 0 <= i < 49 for i in dropped):
            raise InputContractError("Mask must be a tuple of integer indices in [0,48]")
        if tuple(sorted(set(dropped))) != dropped:
            raise InputContractError("Mask indices must be unique and sorted")
        if self.feature_mode not in ("full", "pruned") or (self.feature_mode == "full") != (len(dropped) == 0):
            raise InputContractError("Full requires an empty mask; pruned requires a nonempty mask")
        if set(dropped).intersection(BINARY_INDICES):
            raise InputContractError("Available flags cannot be feature-masked")

    def to_dict(self):
        n = normalizer_spec()
        return dict(schema=INPUT_VERSION, feature_names=list(FEATURE_NAMES),
                    feature_mode=self.feature_mode, zeroed_feature_indices=list(self.zeroed_feature_indices),
                    mask_operation="zero_before_normalize", normalizer=n,
                    normalizer_spec_sha256=sha256(canonical_bytes(n)).hexdigest(), action_mapping=list(ACTIONS))

    @property
    def sha256(self):
        return sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("zeroed_feature_indices"), list):
            raise InputContractError("Missing input specification or feature mask")
        spec = cls(value.get("feature_mode"), tuple(value["zeroed_feature_indices"]))
        # Exact schema comparison also rejects reordered features, scales, action maps and unknown versions.
        if value != spec.to_dict():
            raise InputContractError("Input/normalizer/action contract mismatch")
        return spec


@dataclass(frozen=True)
class PreparedState:
    raw: np.ndarray
    masked: np.ndarray
    normalized: np.ndarray
    available_actions: tuple


def prepare_state(raw_state, spec):
    if not isinstance(spec, InputSpec):
        raise InputContractError("Explicit InputSpec required")
    raw = np.array(raw_state, dtype=np.float64, copy=True)
    if raw.shape != (49,) or not np.isfinite(raw).all() or (raw < 0).any():
        raise InputContractError("Raw state must contain 49 finite nonnegative values")
    flags = raw[list(BINARY_INDICES)]
    if not np.isin(flags, (0., 1.)).all():
        raise InputContractError("Available flags must be binary")
    available = tuple(int(i) for i in np.flatnonzero(flags))
    if not available:
        raise InputContractError("No available actions")
    masked = raw.copy()
    masked[list(spec.zeroed_feature_indices)] = 0.
    normalized = normalize(masked)  # Exactly one normalization, after exactly one feature mask.
    for array in (raw, masked, normalized):
        array.setflags(write=False)
    return PreparedState(raw, masked, normalized, available)


def greedy_action(q_values, available):
    q = np.asarray(q_values)
    if q.shape != (3,) or not np.isfinite(q).all():
        raise InputContractError("Q values must be three finite values")
    choices = tuple(available)
    if not choices or choices != tuple(sorted(set(choices))) or any(type(i) is not int or not 0 <= i < 3 for i in choices):
        raise InputContractError("Invalid available action set")
    # np.argmax preserves the original first/canonical action tie-break.
    return int(choices[int(np.argmax(q[list(choices)]))])


@dataclass(frozen=True)
class ContractRef:
    path: Path
    sha256: str
    source_root: Path


def _source_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise InputContractError("Evidence paths must be relative to the supplied source root")
    path = (Path(root).resolve() / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise InputContractError("Evidence path escapes source root")
    return path


def validate_model_contract(ref, algorithm, checkpoint, expected_sha256):
    if not isinstance(ref, ContractRef):
        raise InputContractError("A trusted checkpoint input contract is required; no Full49 fallback")
    if algorithm not in ("dqn", "ddqn"):
        raise InputContractError("Unknown algorithm")
    try:
        if file_sha256(ref.path) != _digest(ref.sha256):
            raise InputContractError("Model metadata checksum mismatch")
        doc = json.loads(Path(ref.path).read_text(encoding="utf-8"))
        if set(doc) != {"schema", "algorithm", "checkpoint_sha256", "input_spec", "sources", "mask_evidence", "checkpoint_evidence"}:
            raise InputContractError("Incomplete or unexpected model metadata")
        if doc["schema"] != MODEL_VERSION or doc["algorithm"] != algorithm:
            raise InputContractError("Model schema/algorithm mismatch")
        if doc["checkpoint_sha256"] != _digest(expected_sha256) or file_sha256(checkpoint) != expected_sha256:
            raise InputContractError("Checkpoint checksum mismatch")
        spec = InputSpec.from_dict(doc["input_spec"])
        sources = doc["sources"]
        if not isinstance(sources, list) or not sources:
            raise InputContractError("Training/metadata provenance is required")
        seen = set()
        for source in sources:
            if set(source) != {"path", "sha256"} or source["path"] in seen:
                raise InputContractError("Invalid or duplicate evidence source")
            seen.add(source["path"])
            if file_sha256(_source_path(ref.source_root, source["path"])) != _digest(source["sha256"]):
                raise InputContractError("Historical evidence checksum mismatch: " + source["path"])
        binding = doc['checkpoint_evidence']
        if (not isinstance(binding, dict) or set(binding) != {'path', 'field_path'}
                or binding['path'] not in seen or not isinstance(binding['field_path'], list)
                or not binding['field_path'] or any(type(k) is not str or not k for k in binding['field_path'])):
            raise InputContractError('Missing checkpoint-to-metadata binding')
        bound = json.loads(_source_path(ref.source_root, binding['path']).read_text(encoding='utf-8'))
        for key in binding['field_path']:
            bound = bound[key]
        if bound != doc['checkpoint_sha256']:
            raise InputContractError('Historical metadata belongs to a different checkpoint')
        evidence = doc["mask_evidence"]
        if not isinstance(evidence, dict) or evidence.get("path") not in seen:
            raise InputContractError("Mask evidence is not bound to provenance")
        if set(evidence) == {"path", "field"}:
            metadata = json.loads(_source_path(ref.source_root, evidence["path"]).read_text(encoding="utf-8"))
            if metadata.get('checkpoint_sha256', metadata.get('sha256')) != doc['checkpoint_sha256']:
                raise InputContractError('Mask metadata belongs to a different checkpoint')
            if 'algorithm' in metadata and metadata['algorithm'] != algorithm:
                raise InputContractError('Mask metadata algorithm mismatch')
            value = metadata.get(evidence["field"])
            if not isinstance(value, list) or any(type(i) is not int for i in value) or value != list(spec.zeroed_feature_indices):
                raise InputContractError("Feature mask differs from original metadata")
        elif set(evidence) == {"path", "review"}:
            if spec.feature_mode != "full" or evidence["review"] != "verified-full49-training-source":
                raise InputContractError("Only reviewed historical Full49 sources may use the legacy evidence form")
        else:
            raise InputContractError("Missing or invalid feature mask evidence")
        return spec, doc
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InputContractError("Missing or invalid model contract/evidence") from exc


def contract_from_index(index_path, algorithm, checkpoint_sha256):
    if index_path is None:
        raise InputContractError("An explicit contract reference or index is required")
    try:
        index_path = Path(index_path).resolve()
        doc = json.loads(index_path.read_text(encoding="utf-8"))
        if set(doc) != {"schema", "source_root", "models"} or doc["schema"] != INDEX_VERSION:
            raise InputContractError("Invalid contract index")
        matches = [r for r in doc["models"] if r["algorithm"] == algorithm and r["checkpoint_sha256"] == checkpoint_sha256]
        if len(matches) != 1:
            raise InputContractError("Checkpoint contract missing or ambiguous in index")
        row = matches[0]
        return ContractRef(_source_path(index_path.parent, row["contract_path"]),
                           _digest(row["contract_sha256"]), (index_path.parent / doc["source_root"]).resolve())
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InputContractError("Missing or invalid contract index") from exc


def write_model_contract(checkpoint, algorithm, spec, directory, source_root, sources, mask_evidence, checkpoint_evidence):
    """Explicit export only; existing contracts and historical artifacts are never overwritten."""
    root = Path(source_root).resolve()
    directory = Path(directory)
    paths = [Path(p).resolve() for p in sources]
    doc = dict(schema=MODEL_VERSION, algorithm=algorithm, checkpoint_sha256=file_sha256(checkpoint),
               input_spec=spec.to_dict(), sources=[dict(path=p.relative_to(root).as_posix(), sha256=file_sha256(p)) for p in paths],
               mask_evidence=mask_evidence, checkpoint_evidence=checkpoint_evidence)
    payload = canonical_bytes(doc)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{algorithm}-{doc['checkpoint_sha256']}-{spec.sha256}.json"
    if path.exists():
        if path.read_bytes() != payload:
            raise InputContractError("Refusing to overwrite an existing model contract")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
    ref = ContractRef(path.resolve(), sha256(payload).hexdigest(), root)
    validate_model_contract(ref, algorithm, checkpoint, doc["checkpoint_sha256"])
    return ref


def write_contract_index(path, refs):
    """Write a new explicit index; entries are bound by checksum, never inferred from filenames."""
    path = Path(path).resolve()
    refs = list(refs)
    if not refs or len({str(ref.source_root.resolve()) for ref in refs}) != 1:
        raise InputContractError("Index requires contracts sharing one evidence root")
    rows = []
    for ref in refs:
        doc = json.loads(ref.path.read_text(encoding="utf-8"))
        rows.append(dict(algorithm=doc["algorithm"], checkpoint_sha256=doc["checkpoint_sha256"],
                         contract_path=ref.path.relative_to(path.parent).as_posix(), contract_sha256=ref.sha256))
    keys = [(r["algorithm"], r["checkpoint_sha256"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise InputContractError("Duplicate checkpoint contracts")
    doc = dict(schema=INDEX_VERSION, source_root=os.path.relpath(refs[0].source_root, path.parent), models=rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_bytes(doc))


def export_agent_contract(agent, checkpoint, directory, sources):
    """Explicitly attest a newly created run's actual InputSpec, without changing NPZ format."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(dict(algorithm=agent.algorithm, checkpoint_sha256=file_sha256(checkpoint),
                                   feature_mask=list(agent.input_spec.zeroed_feature_indices)))
    metadata = directory / (agent.algorithm + '-' + file_sha256(checkpoint) + '-' + agent.input_spec.sha256 + '-input.json')
    if metadata.exists():
        if metadata.read_bytes() != payload:
            raise InputContractError('Refusing to overwrite input evidence')
    else:
        with metadata.open('xb') as stream:
            stream.write(payload)
    sources = [metadata, *(Path(p).resolve() for p in sources)]
    root = Path(os.path.commonpath([str(p.parent) for p in sources]))
    return write_model_contract(checkpoint, agent.algorithm, agent.input_spec, directory, root, sources,
                                dict(path=metadata.relative_to(root).as_posix(), field='feature_mask'),
                                dict(path=metadata.relative_to(root).as_posix(), field_path=['checkpoint_sha256']))
