from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibethinker_experiments.checkpoints import (
    CheckpointGuardian,
    GuardianConfig,
    checkpoint_save_decision,
    save_checkpoint_if_due,
    validate_committed_checkpoint,
)
from vibethinker_experiments.distillation import (
    CandidateVerdict,
    DistillationConfig,
    DistillationRunner,
    FatalTeacherError,
    JsonProgressStore,
    RetryableTeacherError,
    RetryingTeacherClient,
    RetryPolicy,
    TeacherRequest,
    TeacherResponse,
)
from vibethinker_experiments.persistence import (
    CallbackPublisher,
    build_artifact_manifest,
    publish_results,
    verify_artifact_manifest,
)
from vibethinker_experiments.runtime import (
    ContextProbeConfig,
    build_bundle_manifest,
    build_context_probe_cases,
    context_override,
    evaluate_context_probe,
)
from vibethinker_experiments.verification import (
    CodeVerifier,
    DomainVerifier,
    ExecutionResult,
    IsolatedPythonSubprocessRunner,
    MathVerifier,
    ProtocolVerifier,
    VerificationRequest,
    parse_think_protocol,
)


class FlakyTeacher:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: TeacherRequest) -> TeacherResponse:
        self.calls += 1
        if self.calls < 3:
            raise RetryableTeacherError("temporary")
        return TeacherResponse("reason", "answer", teacher="teacher")


def test_teacher_retry_is_injected_and_bounded() -> None:
    teacher = FlakyTeacher()
    delays: list[float] = []
    client = RetryingTeacherClient(
        teacher,
        RetryPolicy(attempts=3, initial_delay_s=1, maximum_delay_s=2, jitter_s=0),
        sleep=delays.append,
    )
    response = client.complete(TeacherRequest("row", "prompt"))
    assert response.answer == "answer"
    assert teacher.calls == 3
    assert delays == [1, 2]


class FixedTeacher:
    def __init__(self, name: str, answer: str) -> None:
        self.name = name
        self.answer = answer
        self.calls = 0

    def complete(self, request: TeacherRequest) -> TeacherResponse:
        self.calls += 1
        return TeacherResponse("reason", self.answer, teacher=self.name)


class ScoringValidator:
    def validate(self, request: TeacherRequest, response: TeacherResponse) -> CandidateVerdict:
        return CandidateVerdict(True, score=float(len(response.answer)))


def test_distillation_selects_best_teacher_and_resumes(tmp_path: Path) -> None:
    first = FixedTeacher("first", "ok")
    second = FixedTeacher("second", "better")
    progress = JsonProgressStore(tmp_path / "progress.json")
    runner = DistillationRunner(
        [first, second],
        ScoringValidator(),
        progress,
        DistillationConfig(max_workers=2, candidate_rounds=1),
    )
    request = TeacherRequest("row-1", "question")
    result = runner.run([request])
    assert result["row-1"]["teacher"] == "second"
    assert first.calls == second.calls == 1

    resumed = runner.run([request])
    assert resumed == result
    assert first.calls == second.calls == 1
    assert json.loads((tmp_path / "progress.json").read_text())["version"] == 1


def test_distillation_propagates_fatal_teacher_errors(tmp_path: Path) -> None:
    class FatalTeacher:
        def complete(self, request: TeacherRequest) -> TeacherResponse:
            raise FatalTeacherError("invalid credentials or configuration")

    runner = DistillationRunner(
        [FatalTeacher(), FixedTeacher("fallback", "answer")],
        ScoringValidator(),
        JsonProgressStore(tmp_path / "progress.json"),
        DistillationConfig(max_workers=1, candidate_rounds=1),
    )
    with pytest.raises(FatalTeacherError):
        runner.run([TeacherRequest("row-1", "question")])


def test_protocol_and_math_verifiers_share_contract() -> None:
    candidate = "<think>\nwork\n</think>\n42"
    assert parse_think_protocol(candidate) == ("work", "42")
    request = VerificationRequest("math", candidate, reference="42")
    assert ProtocolVerifier().verify(request).passed
    routed = DomainVerifier({"math": MathVerifier()}).verify(request)
    assert routed.passed and routed.verifier == "math"
    assert (
        not ProtocolVerifier()
        .verify(VerificationRequest("math", "<think>x</think><answer>42</answer>"))
        .passed
    )


class FakeCodeRunner:
    def run(self, code: str, stdin: str, timeout_s: float) -> ExecutionResult:
        return ExecutionResult(0, stdout=stdin)


def test_code_verifier_uses_runner_contract_only() -> None:
    verifier = CodeVerifier(FakeCodeRunner())
    result = verifier.verify(
        VerificationRequest(
            "code",
            "<think>plan</think>\n```python\nprint(input())\n```",
            metadata={"inputs": ["a\n", "b\n"], "outputs": ["a", "b"]},
        )
    )
    assert result.passed
    assert result.details == {"passed_cases": 2}
    with pytest.raises(ValueError, match="not a hardened sandbox"):
        IsolatedPythonSubprocessRunner(isolated_environment=False)


def test_checkpoint_commit_schedule_and_guardian(tmp_path: Path) -> None:
    assert checkpoint_save_decision(
        global_step=7,
        save_frequency=0,
        is_last_step=True,
    ).should_save
    assert not checkpoint_save_decision(global_step=7, save_frequency=0).should_save

    checkpoint = tmp_path / "checkpoint"

    class Store:
        def save(self, path: Path, step: int) -> None:
            path.mkdir()
            (path / "state.bin").write_bytes(f"state-{step}".encode())

    decision = save_checkpoint_if_due(
        Store(),
        checkpoint,
        global_step=10,
        save_frequency=10,
        required_files=["state.bin"],
    )
    assert decision.reasons == ("periodic",)
    assert validate_committed_checkpoint(checkpoint)["global_step"] == 10

    publications: list[int] = []

    class Publisher:
        def publish(self, path: Path, step: int, metadata: dict) -> dict:
            publications.append(step)
            return {"stored": True}

    guardian = CheckpointGuardian(Publisher(), GuardianConfig(every_n_steps=10))
    assert guardian.publish_if_due(checkpoint, global_step=10).should_publish
    assert not guardian.publish_if_due(checkpoint, global_step=15).should_publish
    assert publications == [10]

    (checkpoint / "state.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="file mismatch"):
        validate_committed_checkpoint(checkpoint)


def test_atomic_manifest_and_callback_publication(tmp_path: Path) -> None:
    (tmp_path / "result.jsonl").write_text('{"value":1}\n')
    manifest = build_artifact_manifest(
        tmp_path,
        ["result.jsonl"],
        metadata={"kind": "test"},
    )
    verify_artifact_manifest(tmp_path, manifest)
    observed: list[str] = []

    def upload(root: Path, manifest_path: Path, value: dict) -> dict:
        observed.append(value["content_sha256"])
        assert manifest_path.is_file()
        return {"location": "injected-adapter"}

    publication = publish_results(
        tmp_path,
        ["result.jsonl"],
        CallbackPublisher(upload),
        metadata={"kind": "test"},
    )
    assert publication.receipt_path.is_file()
    assert publication.receipt["publication"]["location"] == "injected-adapter"
    assert observed == [publication.manifest["content_sha256"]]


class WordTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text.split())))

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        return messages[0]["content"]


def test_runtime_manifest_and_context_probe_are_pure(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('a')\n")
    (tmp_path / "b.json").write_text("{}\n")
    first = build_bundle_manifest(tmp_path, ["b.json", "a.py"], configuration={"seed": 1})
    second = build_bundle_manifest(tmp_path, ["a.py", "b.json"], configuration={"seed": 1})
    assert first == second
    assert [item["path"] for item in first["files"]] == ["a.py", "b.json"]

    config = ContextProbeConfig(
        max_context_tokens=140,
        target_prompt_tokens=120,
        max_output_tokens=10,
        needle_positions=(20, 60),
    )
    cases = build_context_probe_cases(WordTokenizer(), config)
    completions = [f"answer {case.key}" for case in cases]
    report = evaluate_context_probe(cases, completions)
    assert report["all_matched"]
    assert context_override(32_000, 65_536) == {"max_position_embeddings": 65_536}
    assert context_override(65_536, 65_536) is None


def test_manifests_reject_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe and relative"):
        build_artifact_manifest(tmp_path, ["../outside"])
