# Publishability rubric (v2)

How `triage.py` decides whether a note becomes a draft. The model scores and quotes evidence; **code** verifies, caps, weights and decides. Weights, caps and the threshold live in `triage.py` and `config.py`, which are the source of truth if this page ever disagrees.

## Parameters

| Parameter | Weight | Question | Guardrail |
|---|---|---|---|
| Founder Relevance | 1.0 | Does it come from Meera's own role, formulation expertise, business or founder journey? | fail if outside her expertise but presented as authority |
| Audience Relevance | 1.0 | Does it matter to urban Indian women buying skincare, and industry peers? | warn if only a niche with no link to her audience |
| Originality | 1.5 | A non-generic observation, not a repeat of her published pieces? | fail if it restates a published piece or is generic advice |
| Insight Depth | 1.0 | Is there a mechanism or a "why"? | warn if surface-level |
| Authenticity | 1.5 | Something she experienced, observed, tested or believes? | fail if it can't reasonably be attributed to her |
| Practical Value | 1.0 | Does the reader get a lesson, check or takeaway? | warn if no takeaway |
| Credibility | 1.5 | Supported by her experience, evidence or reasoning? | warn for sweeping claims; fail for unsupported factual or statistical claims |
| LinkedIn Fit | 0.5 | Would it naturally become a founder-led LinkedIn post? | warn if it only works as bait |
| Discussion Potential | 0.5 | Could it start thoughtful discussion without bait? | fail if it depends on attacking someone |
| Postability | 1.5 | Could it become a standalone post without inventing facts, stories or numbers? | fail if it would need invented material |

## Code-side checks

1. **Evidence:** each score must quote the transcript. A quote is verified if it has at least 3 words and at least 80% of them appear in the note. Unverified evidence caps that parameter at **5**.
2. **Guardrail caps:** `pass` = 10, `warn` = 6, `fail` = 2.
3. **Overall:** Σ(weight × score) ÷ Σ(weight), rounded half-up to one decimal.
4. **Hard flags:** any model flag (fabricated information, private customer data, defamation and so on) or a code-detected email address, phone number or ID-like number sends the note to **human review**, whatever its score.
5. **Decision:** no flags and overall **strictly above** `TRIAGE_THRESHOLD` (default 8) = qualified; otherwise rejected, with the three weakest parameters' gaps as improvement tips and three topic suggestions.
6. **Before any model call:** notes shorter than `TRIAGE_MIN_WORDS` are rejected, and voice transcripts with low clarity or too many `[unclear]` words go to human review.
