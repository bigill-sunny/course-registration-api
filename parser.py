from bs4 import BeautifulSoup
import re


def normalize_course_code(value: str) -> str:
    """Remove whitespace from a course code."""

    return re.sub(r"\s+", "", value.strip())


def extract_course_codes(value: str) -> list[str]:
    """
    Extract course codes from prerequisite or cross-listed text.

    Handles course codes such as:
        COSC 2007
        COSC2007
        ITEC 3506
        ABCDE 1234
    """

    if not value or value.strip().lower() == "none":
        return []

    matches = re.findall(
        r"\b[A-Za-z]{2,10}\s*\d{3,4}\b",
        value
    )

    return [
        normalize_course_code(code)
        for code in matches
    ]


def parse_catalog(html: str) -> list[dict]:
    """Parse an HTML course catalog and return structured course data."""

    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")

    if table is None:
        raise ValueError("No catalog table found.")

    # Find the header row.
    header_row = table.find("thead")

    if header_row is None:
        raise ValueError("Catalog table has no header.")

    headers = [
        header.get_text(" ", strip=True).lower()
        for header in header_row.find_all("th")
    ]

    # Map normalized header names to their column positions.
    header_map = {
        header: index
        for index, header in enumerate(headers)
    }

    required_headers = [
        "course code",
        "title",
        "credits",
        "prerequisites",
        "cross-listed",
    ]

    for required_header in required_headers:
        if required_header not in header_map:
            raise ValueError(
                f"Missing required catalog column: {required_header}"
            )

    courses = []

    tbody = table.find("tbody")

    if tbody is None:
        raise ValueError("Catalog table has no course rows.")

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")

        if not cells:
            continue

        # Make sure this row has enough columns.
        if len(cells) < len(headers):
            continue

        course_code = normalize_course_code(
            cells[header_map["course code"]].get_text(" ", strip=True)
        )

        title = cells[header_map["title"]].get_text(
            " ", strip=True
        )

        credits_text = cells[header_map["credits"]].get_text(
            " ", strip=True
        )

        prerequisites_text = cells[
            header_map["prerequisites"]
        ].get_text(" ", strip=True)

        cross_listed_text = cells[
            header_map["cross-listed"]
        ].get_text(" ", strip=True)

        try:
            credits = int(credits_text)
        except ValueError:
            raise ValueError(
                f"Invalid credits value for {course_code}: "
                f"{credits_text}"
            )

        course = {
            "course_code": course_code,
            "title": title,
            "credits": credits,
            "prerequisites": extract_course_codes(
                prerequisites_text
            ),
            "cross_listed": extract_course_codes(
                cross_listed_text
            ),
        }

        courses.append(course)

    return courses