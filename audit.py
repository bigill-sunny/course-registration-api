import re

from parser import course_key
from students import Profile

SEASON_ORDER = {"W": 0, "SP": 1, "S": 2, "F": 3}
GRADUATION_CREDITS = 120


def term_order(term: str) -> tuple[int, int]:
    match = re.fullmatch(r"([0-9]{2})(W|SP|S|F)", term)
    if match:
        return int(match[1]), SEASON_ORDER[match[2]]
    return 100, 0


def build_audit(profile: Profile, catalog: list[dict], strict: bool) -> dict:
    courses = {course_key(course["course_code"]): course for course in catalog}
    earliest_completion = {}
    earned_by_course = {}
    for record in profile.history:
        if record.status != "Completed":
            continue
        code = course_key(record.course_code)
        term = term_order(record.term)
        earliest_completion[code] = min(term, earliest_completion.get(code, term))
        # Use the latest completed attempt when credit values differ.
        rank = (term, record.credits_earned)
        if code not in earned_by_course or rank > earned_by_course[code]:
            earned_by_course[code] = rank

    errors_by_term = {}
    cross_list_violations = []
    total_planned = 0
    for planned in profile.plan:
        course = courses.get(course_key(planned.course_code))
        if course is None:
            continue
        total_planned += course["credits"]
        planned_term = term_order(planned.term)
        prerequisites = {course_key(code): code for code in course["prerequisites"]}
        for key, code in prerequisites.items():
            completed = earliest_completion.get(key)
            if (
                completed is None
                or planned_term == (100, 0)
                or completed >= planned_term
            ):
                errors_by_term.setdefault(planned.term, []).append(
                    {
                        "course_code": planned.course_code,
                        "type": "MISSING_PREREQUISITE",
                        "message": f"Missing prerequisite: {code}",
                    }
                )
        cross_listed = {course_key(code): code for code in course["cross_listed"]}
        for key, code in cross_listed.items():
            if key in earned_by_course:
                cross_list_violations.append(
                    {
                        "course_code": planned.course_code,
                        "type": "CROSS_LIST_CONFLICT",
                        "message": f"Cross-listed with completed course {code}",
                    }
                )

    status = "ok"
    if errors_by_term or cross_list_violations:
        status = "failed" if strict else "warning"
    total_earned = sum(credits for _, credits in earned_by_course.values())
    return {
        "student_id": profile.student_id,
        "status": status,
        "timeline_validation": [
            {"term": term, "errors": errors_by_term[term]}
            for term in sorted(errors_by_term, key=term_order)
        ],
        "cross_list_violations": cross_list_violations,
        "credit_summary": {
            "total_earned": total_earned,
            "total_planned": total_planned,
            "total_remaining_for_graduation": max(
                0, GRADUATION_CREDITS - total_earned - total_planned
            ),
        },
    }
