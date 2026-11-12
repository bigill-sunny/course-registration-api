from dataclasses import dataclass, field
import re
from threading import Lock
from typing import Annotated

from bs4 import BeautifulSoup
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, StringConstraints

router = APIRouter(prefix="/api/v1/students", tags=["students"])
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PAST_STATUSES = {"Completed", "In-Progress", "Attempted"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class PlannedCourse(BaseModel):
    course_code: NonEmptyText
    term: NonEmptyText


class PastCourse(PlannedCourse):
    credits_earned: int
    status: NonEmptyText


class HistoryUpdate(BaseModel):
    history: list[PastCourse]


class PlanUpdate(BaseModel):
    planned_courses: list[PlannedCourse]


class Profile(BaseModel):
    student_id: str
    history: list[PastCourse]
    plan: list[PlannedCourse]


@dataclass
class Student:
    history: list[PastCourse] = field(default_factory=list)
    plan: list[PlannedCourse] = field(default_factory=list)


students: dict[str, Student] = {}
students_lock = Lock()


def grade_rank(grade: str) -> tuple[int, float]:
    if re.fullmatch(r"\d+(\.\d+)?", grade):
        return 2, float(grade)
    if re.fullmatch(r"[A-F][+-]?", grade, re.IGNORECASE):
        return 1, 0.0
    return 0, 0.0


def parse_history(html: str) -> list[PastCourse]:
    soup = BeautifulSoup(html, "html.parser")
    best: dict[tuple[str, str], tuple[tuple[int, float, int], PastCourse]] = {}
    transcript_found = False
    for table in soup.find_all("table"):
        headers = {cell.get_text(strip=True) for cell in table.find_all("th")}
        if not {"Status", "Course", "Credits"} <= headers:
            continue
        transcript_found = True
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            if len(cells) < 6:
                continue
            status, code, _, grade, term, credits = cells[:6]
            if status not in PAST_STATUSES or not code or not term:
                continue
            try:
                credits_earned = int(credits)
            except ValueError:
                credits_earned = 0

            key = (code, term)
            rank = (*grade_rank(grade), credits_earned)
            if key not in best or rank > best[key][0]:
                best[key] = (
                    rank,
                    PastCourse(
                        course_code=code,
                        term=term,
                        credits_earned=credits_earned,
                        status=status,
                    ),
                )

    if not transcript_found:
        raise ValueError("No transcript table found")
    return [course for _, course in best.values()]


def find_student(student_id: str) -> Student:
    try:
        return students[student_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Student not found") from None


@router.post("/{student_id}/history/import", status_code=201)
def import_history(student_id: str, file: UploadFile = File(...)):
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Transcript exceeds 8 MiB")
    try:
        history = parse_history(contents.decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400, detail="Transcript must be UTF-8"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with students_lock:
        student = students.setdefault(student_id, Student())
        student.history = history
    return {"status": "success", "past_courses_imported": len(history)}


@router.put("/{student_id}/history")
def replace_history(student_id: str, update: HistoryUpdate):
    with students_lock:
        find_student(student_id).history = update.history
    return {"status": "success", "message": "Academic history updated successfully"}


@router.delete("/{student_id}/history", status_code=204)
def delete_history(student_id: str):
    with students_lock:
        find_student(student_id).history = []


@router.post("/{student_id}/plan")
def add_plan(student_id: str, update: PlanUpdate):
    with students_lock:
        student = find_student(student_id)
        plan = {
            (course.course_code, course.term): course
            for course in student.plan + update.planned_courses
        }
        student.plan = list(plan.values())
        return {"status": "success", "planned_courses_saved": len(student.plan)}


@router.put("/{student_id}/plan")
def replace_plan(student_id: str, update: PlanUpdate):
    with students_lock:
        find_student(student_id).plan = update.planned_courses
    return {"status": "success", "planned_courses_saved": len(update.planned_courses)}


@router.delete("/{student_id}/plan", status_code=204)
def delete_plan(student_id: str):
    with students_lock:
        find_student(student_id).plan = []


@router.get("/{student_id}/profile")
def get_profile(student_id: str) -> Profile:
    with students_lock:
        student = find_student(student_id)
        return Profile(
            student_id=student_id, history=student.history, plan=student.plan
        )
