from fastapi import FastAPI, File, UploadFile, HTTPException

from parser import parse_catalog


app = FastAPI(
    title="Course Registration API",
    version="1.0.0"
)


# Application memory.
# This will contain the most recently imported catalog.
catalog = []


@app.get("/")
def root():
    return {
        "message": "Course Registration API is running"
    }


@app.post("/api/v1/admin/catalog/import")
async def import_catalog(file: UploadFile = File(...)):
    global catalog

    # Make sure the uploaded file is HTML.
    if file.content_type not in ["text/html", "application/xhtml+xml"]:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an HTML file."
        )

    try:
        contents = await file.read()

        html = contents.decode("utf-8")

        parsed_courses = parse_catalog(html)

        catalog = parsed_courses

        return {
            "message": "Catalog imported successfully",
            "courses_imported": len(catalog)
        }

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not decode the uploaded HTML file."
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )
@app.get("/api/v1/catalog/courses/{course_code}")
def get_course(course_code: str):

    normalized_code = course_code.replace(" ", "").upper()

    for course in catalog:
        if course["course_code"].upper() == normalized_code:
            return course

    raise HTTPException(
        status_code=404,
        detail="Course not found"
    )