"""Advisor assistant built on top of the statistical model.

What it does: drafts respectful check-in messages, writes short case briefs, answers questions about
group-level patterns. What it never does: score students (that is the calibrated model's job),
send anything to a student, or see identifiers.

Safety design:
* Case-level prompts contain only qualitative, de-identified statements. No IDs, names, program,
  term, dates or numbers. Group-level prompts contain only aggregate statistics.
* Which provider may see which level is enforced in llm.eligible() from the administrator's setting.
* All model output is validated. Anything that fails falls back to a deterministic template or
  rule-based brief, so the feature always works, with or without an AI provider.
* Every draft or brief is marked as needing human review.
"""
import json
import re

from . import llm
from .llm import LLMError
from .utilities.common import get_gemini_key, key_source, load_config, mask_key

AREA_TEXT = {
    "academic": "coursework and study support",
    "workload": "assignments and deadlines",
    "attendance": "getting to classes or sessions",
    "engagement": "the online learning platform, devices or connectivity",
    "admin": "fees, registration or funding",
    "general": "how the term is going",
}

TEMPLATE_LINES = {
    "academic": "If any course feels harder than expected, there are tutoring and study-planning options we can look at together.",
    "workload": "If deadlines have been piling up, we can work out a plan that feels manageable.",
    "attendance": "If getting to class or sessions has been tough lately, we are happy to talk about flexible options.",
    "engagement": "If anything about the online platform, your devices or your connection has been getting in the way, we can help with that.",
    "admin": "If questions about fees, registration or funding are on your mind, our team can walk you through the options.",
    "general": "We would like to hear how things are going and whether anything would make the term easier.",
}

STARTERS = {
    "academic": "Which of your courses feels most challenging right now?",
    "workload": "Are there deadlines or tools that have been hard to keep on top of?",
    "attendance": "Has anything been making it hard to get to classes or sessions, like work or transport?",
    "engagement": "Is anything getting in the way of using the online course platform?",
    "admin": "Do you have any questions about fees or registration we could help with?",
}

# Message drafts must never sound like surveillance or a verdict.
FORBIDDEN = re.compile(
    r"drop\s?-?out|at[- ]risk|risk|predict|algorithm|artificial|\bAI\b|score|flagged|monitor|data|track|surveil|\d",
    re.IGNORECASE,
)
# Briefs must not speculate about health, family, status or protected characteristics.
SENSITIVE = re.compile(
    r"drop\s?-?out|diagnos|depress|anxiety|mental ill|immigra|visa\b|disabilit|ethnic|\brace\b|religio|pregnan|divorce|abus|"
    r"gender|sexual|will (?:leave|quit|fail)|going to (?:leave|quit|fail)",
    re.IGNORECASE,
)
ID_LIKE = re.compile(r"\b[A-Za-z]{1,5}-\d{3,}\b")

DRAFT_SYSTEM = (
    "You write short, warm, non-judgmental check-in messages from a university advisor to a student. "
    "Never mention predictions, risk, algorithms, data, monitoring, scores or grades, and never use numbers. "
    "Do not say the student is struggling or failing. Offer help and a short private conversation. "
    "Keep it under 90 words. Use the placeholders [Student name] and [Advisor name]. Output only the message."
)

BRIEF_SYSTEM = (
    "You help university advisors prepare a supportive conversation with a student. You receive de-identified, "
    "qualitative facts from a statistical early-warning model. The estimate reflects statistical association, not "
    "cause, and it can be wrong. Return JSON only, with exactly these keys: "
    '"summary" (2 or 3 plain, non-judgmental sentences), '
    '"conversation_starters" (3 warm, open-ended questions or openers), '
    '"support_priority" (up to 4 objects with "support" and "why"), '
    '"cautions" (1 to 3 items: alternative explanations and things not to assume). '
    "Never predict that the student will leave or fail. Never guess at health, family, finances, immigration, "
    "disability, or any personal characteristic. Never invent facts or numbers that were not given."
)

ASK_SYSTEM = (
    "You are the analytics assistant inside EduGuard, used by university student-support staff. Answer ONLY from the "
    "JSON data provided. If the data does not contain the answer, say so plainly. The data is aggregate. Never speculate "
    "about individual students and do not ask for names or IDs. Describe patterns as associations, not causes. Mention "
    "small samples and uncertainty where relevant. Differences between groups are a reason to check that support is fair, "
    "never a reason to treat students differently or to withhold services. Use plain language, short paragraphs, and "
    "hyphen bullets if a list helps. No markdown headings or bold. Keep it under 220 words."
)


# ------------------------------------------------------------------ status
def status():
    cfg = load_config()["assistant"]
    key = get_gemini_key()
    aggregate, case = llm.eligible("aggregate"), llm.eligible("case")
    return {
        "provider_preference": cfg["provider"],
        "gemini": {"key_saved": bool(key), "key_hint": mask_key(key), "key_source": key_source(), "mode": cfg["gemini_mode"],
                   "model": cfg["gemini_model"], "attested": bool(cfg["gemini_attested"])},
        "ollama": llm.ollama_status(),
        "aggregate_provider": aggregate[0] if aggregate else None,
        "case_provider": case[0] if case else None,
    }


# ------------------------------------------------------------------ de-identification
QUAL_RAISING = {
    "attendance_rate": "attendance is low", "attendance_change": "attendance has been falling",
    "assignment_completion": "many assignments are not being completed", "assignment_change": "assignment completion has been falling",
    "gpa": "current grades are low", "gpa_change": "grades have dropped since last term",
    "failed_courses": "there are failed courses on record", "credit_ratio": "few attempted credits have been earned",
    "lms_days": "there is little activity on the learning platform", "lms_change": "platform activity has been falling",
    "advising_visits": "there have been no advising visits this term", "fee_hold": "an account hold is open",
    "registration_delay_days": "registration was late",
}
QUAL_PROTECTIVE = {
    "attendance_rate": "attendance is good", "assignment_completion": "assignments are being completed",
    "gpa": "grades are solid", "lms_days": "the student is regularly active on the learning platform",
    "advising_visits": "the student has met with an advisor", "fee_hold": "there is no account hold",
    "registration_delay_days": "registration was on time", "failed_courses": "there are no failed courses on record",
    "credit_ratio": "most attempted credits have been earned",
}
TREND_LABELS = {"Attendance": "attendance", "Assignments": "assignment completion", "Platform activity": "learning platform activity", "GPA": "grades"}
FACT_LABELS = {
    "Missed submissions": "some submissions have been missed", "Late submissions": "some submissions were handed in late",
    "Inactive weeks": "there were weeks with no platform activity", "Account": "an account hold is open",
    "Registration": "registration was late",
}


def deidentify_case(item, exp, changes, conf, focus):
    """Turn a student's record into qualitative statements. No ID, name, program, term, dates or numbers."""
    change = item.get("change")
    movement = "new this term" if change is None else "rising" if change >= 0.03 else "falling" if change <= -0.03 else "steady"
    recent = []
    for c in changes:
        if c["label"] in TREND_LABELS and c["tone"] in ("worse", "better"):
            recent.append(f"{TREND_LABELS[c['label']]} has {'declined' if c['tone'] == 'worse' else 'improved'} in the last few weeks")
        elif c["label"] in FACT_LABELS:
            recent.append(FACT_LABELS[c["label"]])
    dedupe = lambda seq: list(dict.fromkeys(x for x in seq if x))
    return {
        "estimate_band": item["band"],
        "movement_since_last_term": movement,
        "confidence_in_estimate": conf["level"] if conf else "unknown",
        "signals_raising_the_estimate": dedupe(QUAL_RAISING.get(s["feature"]) for s in exp["raising"]),
        "signals_lowering_the_estimate": dedupe(QUAL_PROTECTIVE.get(s["feature"]) for s in exp["protective"]),
        "recent_changes": dedupe(recent),
        "possible_support_areas": [AREA_TEXT[c] for c in focus if c in AREA_TEXT],
    }


# ------------------------------------------------------------------ message drafts
def template_message(areas, channel="Email", tone="warm"):
    areas = [a for a in areas if a in TEMPLATE_LINES] or ["general"]
    lines = ["Hi [Student name],", "", "I wanted to check in and see how your term is going."]
    limit = 1 if tone == "brief" or channel == "Text message" else 2
    for area in areas[:limit]:
        lines.append(TEMPLATE_LINES[area])
    if channel == "Text message":
        lines.append("Would you like to chat privately this week? - [Advisor name]")
    else:
        lines += ["", "There is no obligation, and anything you share stays with the people who support you.",
                  "Would you like to set up a short, private conversation at a time that suits you?", "",
                  "Best wishes,", "[Advisor name]"]
    return "\n".join(lines)


def draft(areas, channel="Email", tone="warm"):
    fallback = {"message": template_message(areas, channel, tone), "source": "template", "requires_human_review": True,
                "notice": "Review and personalise before sending. Nothing is sent automatically."}
    if not llm.eligible("case"):
        return fallback
    topics = "; ".join(AREA_TEXT.get(a, AREA_TEXT["general"]) for a in (areas[:2] or ["general"]))
    prompt = f"Areas where support may help: {topics}.\nChannel: {channel}.\nTone: {tone}.\nWrite the message now."
    try:
        text, provider = llm.generate(DRAFT_SYSTEM, prompt, "case", max_tokens=600, temperature=0.4)
    except LLMError as exc:
        return {**fallback, "ai_note": str(exc)}
    body = text.replace("[Student name]", "").replace("[Advisor name]", "")
    if not text or len(text.split()) > 130 or FORBIDDEN.search(body):
        return {**fallback, "ai_note": "The AI's wording didn't pass the safety check, so a template is shown."}
    return {**fallback, "message": text, "source": provider}


# ------------------------------------------------------------------ case brief
def rules_brief(facts, recs, focus):
    """Deterministic brief used when no AI provider is available or its output fails validation."""
    raising = facts["signals_raising_the_estimate"][:3]
    summary = f"The estimate is {facts['estimate_band'].lower()} and {facts['movement_since_last_term']} compared with last term."
    if raising:
        summary += " What stands out: " + "; ".join(raising) + "."
    starters = ["How has this term been going for you so far?", "Is there anything that has made it harder to keep up recently?"]
    starters += [STARTERS[c] for c in focus if c in STARTERS][:2]
    starters.append("What would make the rest of the term easier?")
    return {
        "summary": summary,
        "conversation_starters": starters[:4],
        "support_priority": [{"support": r["suggested_type"], "why": "Possible fit for: " + r["title"].lower()} for r in recs][:4],
        "cautions": ["This is an estimate based on patterns, not a judgement about the student.",
                     "Other explanations are possible. Ask before assuming anything."],
    }


def _clean_list(value, limit, size):
    if not isinstance(value, list):
        return None
    out = [str(v).strip()[:size] for v in value if isinstance(v, str) and v.strip()]
    return out[:limit] or None


def _validate_brief(raw):
    """Return a clean brief or None if the AI's output is malformed or unsafe."""
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("summary"), str):
        return None
    starters = _clean_list(data.get("conversation_starters"), 4, 240)
    cautions = _clean_list(data.get("cautions"), 3, 240)
    support = []
    for s in (data.get("support_priority") or [])[:4]:
        if isinstance(s, dict) and isinstance(s.get("support"), str):
            support.append({"support": s["support"].strip()[:120], "why": str(s.get("why", "")).strip()[:240]})
    if not (starters and cautions and support):
        return None
    brief = {"summary": data["summary"].strip()[:700], "conversation_starters": starters, "support_priority": support, "cautions": cautions}
    flat = json.dumps(brief)
    if SENSITIVE.search(flat) or ID_LIKE.search(flat):
        return None
    return brief


def case_brief(facts, recs, focus):
    fallback = {"brief": rules_brief(facts, recs, focus), "source": "rules", "shared": None, "requires_human_review": True}
    if not llm.eligible("case"):
        return fallback
    prompt = "De-identified facts about one student this term (JSON):\n" + json.dumps(facts, indent=1)
    try:
        text, provider = llm.generate(BRIEF_SYSTEM, prompt, "case", json_mode=True, max_tokens=2048, temperature=0.3)
    except LLMError as exc:
        return {**fallback, "ai_note": str(exc)}
    brief = _validate_brief(text)
    if brief is None:
        return {**fallback, "ai_note": "The AI's answer didn't pass the safety check, so a rule-based brief is shown."}
    return {**fallback, "brief": brief, "source": provider, "shared": facts, "external": provider == "gemini"}


# ------------------------------------------------------------------ group-level Q&A
def _plain(text):
    text = re.sub(r"\*\*|__|^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def ask(question, history, context):
    turns = "\n".join(f"{'Staff' if h['role'] == 'user' else 'Assistant'}: {h['text']}" for h in history)
    prompt = ("DATA (JSON, group-level only):\n" + json.dumps(context, separators=(",", ":"))
              + ("\n\nCONVERSATION SO FAR:\n" + turns if turns else "") + f"\n\nQUESTION: {question}")
    text, provider = llm.generate(ASK_SYSTEM, prompt, "aggregate", max_tokens=2048, temperature=0.2)
    return {"answer": _plain(text), "source": provider, "external": provider == "gemini"}
