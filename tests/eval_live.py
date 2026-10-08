"""Live checks against real Gemini and Google News. Not part of pytest; needs a real .env.

Usage:
  python tests/eval_live.py triage          # scorecards for the sample notes
  python tests/eval_live.py draft [--save]  # news + draft + QA for notes that qualify
  python tests/eval_live.py qa              # an injected fabricated statistic must be caught
  python tests/eval_live.py probe [N]       # draft one note N times; count invented numbers or studies
  python tests/eval_live.py news            # one real Google News fetch
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import draft  # noqa: E402
import news  # noqa: E402
import triage  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES: dict[str, str] = json.loads((FIXTURES / "sample_notes.json").read_text(encoding="utf-8"))
BASELINE = FIXTURES / "last_good_drafts.json"


def scratch_db() -> None:
    path = Path(__file__).parent / ".eval.db"
    path.unlink(missing_ok=True)
    db.init_db(path)


async def assess(key: str, text: str, message_id: int) -> triage.TriageResult | None:
    note_id = db.add_note(message_id, 0, text, datetime.now(UTC))
    return await triage.assess_note(db.get_note(note_id))


async def run_triage() -> dict[str, triage.TriageResult]:
    results = {}
    for n, (key, text) in enumerate(SAMPLES.items(), start=1):
        result = await assess(key, text, n)
        if result is None:
            print(f"{key}: unusable model output")
            continue
        results[key] = result
        print(f"{key}: {result.overall:.1f} {result.decision} category={result.category} flags={len(result.hard_flags)}")
    return results


async def run_draft(save: bool) -> None:
    drafts = {}
    for key, result in (await run_triage()).items():
        if not result.qualified:
            continue
        made = await draft.draft_note(SAMPLES[key], result.category, result.angle,
                                      result.summary.get("core_idea", ""), result.news_keywords)
        print(f"\n===== {key} =====\n{made.body if made else '(dropped: no draft passed validation)'}")
        if made:
            drafts[key] = made.body
    if save:
        BASELINE.write_text(json.dumps(drafts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nSaved {len(drafts)} drafts to {BASELINE.name}")


async def run_qa() -> None:
    note = SAMPLES["batch14"]
    body = ("Batch fourteen came back with the pH down 0.4 units after we changed preservative supplier. "
            "A 2025 study of 3,000 formulations found this happens in 41% of supplier changes.\n\n"
            "The ingredient list stayed identical.\n\nAsk brands how they qualify a new supplier.")
    problems, _ = await draft.fact_check(body, draft.sources_text(note, None))
    print("CAUGHT" if problems else "MISSED", problems)


async def run_probe(times: int) -> None:
    note = SAMPLES["batch14"]
    invented = 0
    for n in range(times):
        made = await draft.make_draft(note, "Industry Transparency", "", draft.pick_exemplars("Industry Transparency"))
        bad = bool(made and (draft.unsupported_numbers(made.body, note)
                             or draft.unsupported_research_claims(made.body, note)))
        invented += bad
        print(f"run {n + 1}: {'dropped' if made is None else 'INVENTED' if bad else 'clean'}")
    print(f"invented in {invented}/{times} delivered drafts (target 0)")


async def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "triage"
    scratch_db()
    if mode == "triage":
        await run_triage()
    elif mode == "draft":
        await run_draft("--save" in sys.argv)
    elif mode == "qa":
        await run_qa()
    elif mode == "probe":
        await run_probe(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
    elif mode == "news":
        for item in await news.fetch_news("sunscreen India"):
            print(item)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
