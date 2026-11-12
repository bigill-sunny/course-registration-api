from fastapi import FastAPI, File, UploadFile, HTTPException

from audit import build_audit
from parser import course_key, parse_catalog
from students import get_profile, router as students_router

app = FastAPI(title="Course Registration API", version="3.0.0")
app.include_router(students_router)


# Application memory.
# This will contain the most recently imported catalog.
catalog = []


@app.get("/")
def root():
    return {"message": "Course Registration API is running"}


@app.post("/api/v1/admin/catalog/import")
async def import_catalog(file: UploadFile = File(...)):
    global catalog

    # Make sure the uploaded file is HTML.
    if file.content_type not in ["text/html", "application/xhtml+xml"]:
        raise HTTPException(
            status_code=400, detail="Uploaded file must be an HTML file."
        )

    try:
        contents = await file.read()

        html = contents.decode("utf-8")

        parsed_courses = parse_catalog(html)

        catalog = parsed_courses

        return {
            "message": "Catalog imported successfully",
            "courses_imported": len(catalog),
        }

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="Could not decode the uploaded HTML file."
        )

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/api/v1/catalog/courses/{course_code}")
def get_course(course_code: str):

    normalized_code = course_key(course_code)

    for course in catalog:
        if course_key(course["course_code"]) == normalized_code:
            return course

    raise HTTPException(status_code=404, detail="Course not found")


@app.get("/api/v1/students/{student_id}/audit-report", tags=["students"])
def audit_report(student_id: str, strict: bool = False):
    return build_audit(get_profile(student_id), catalog, strict)
