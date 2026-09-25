# Voice corpus

`corpus_index.json` maps each piece id to `{source_id, format, category, title, path}`. `format` is `linkedin` or `newsletter`; newsletters open with `Hi,` and end with `Meera` (both stripped when used as exemplars). Categories here become the triage categories.

**These seven pieces are stand-ins.** They were reconstructed from the openings, facts and phrasing quoted in `PLAN.md` §2 and the voice skill, because Meera's 15 published pieces (`published/`, from `3_Voice.pdf`) were not in the repository. Replace them with her real pieces before relying on the drafts' voice: one `.txt` per piece, plus an entry in `corpus_index.json`, then run `pytest` and `tests/eval_live.py draft`.
