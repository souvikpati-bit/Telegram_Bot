import db
from conftest import CAPTURE_CHAT, NOW, add_text_note


def test_add_note_is_idempotent() -> None:
    first = db.add_note(7, CAPTURE_CHAT, "a note", NOW)
    assert first is not None
    assert db.add_note(7, CAPTURE_CHAT, "a note", NOW) is None
    assert [n.id for n in db.get_new_notes()] == [first]


def test_schema_is_current() -> None:
    assert db.schema_version() == len(db.MIGRATIONS)


def test_claim_is_exclusive_until_released() -> None:
    note_id = add_text_note("a note")
    assert db.claim_note(note_id, 60)
    assert not db.claim_note(note_id, 60)
    db.release_note(note_id)
    assert db.claim_note(note_id, 60)


def test_run_slot_is_idempotent() -> None:
    run_id = db.start_run("sweep-2026-09-25-0900")
    assert run_id is not None
    assert db.start_run("sweep-2026-09-25-0900") is None
    assert db.finish_run(run_id, "no_candidate", "nothing pending")
    assert not db.finish_run(run_id, "drafted")
    assert db.get_last_outcome() == "no_candidate"


def test_draft_review_lifecycle_keeps_ai_draft_and_final_text_apart() -> None:
    note_id = add_text_note("a note")
    first = db.add_draft(note_id, "AI draft body", "model-x", [1, 2], None, None, None)
    assert db.start_edit(first)
    assert db.get_awaiting_edit().id == first
    second = db.add_revision(first, "Meera's own rewrite", db.MEERA_EDIT_MODEL)
    assert second is not None
    assert db.get_draft(first).status == "superseded"
    assert db.get_awaiting_edit() is None
    assert db.approve_draft(second)
    assert not db.approve_draft(second)
    final = db.get_final_post(second)
    assert final.final_body == "Meera's own rewrite"
    assert final.ai_draft_body == "AI draft body"
    assert final.edited_by_meera
    assert db.mark_posted(second)
    assert not db.mark_posted(second)


def test_rejected_draft_cannot_be_approved() -> None:
    note_id = add_text_note("a note")
    draft_id = db.add_draft(note_id, "body", "model-x", [], None, None, None)
    assert db.set_draft_status(draft_id, "discarded")
    assert not db.approve_draft(draft_id)
