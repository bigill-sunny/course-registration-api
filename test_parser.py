from pathlib import Path

from parser import parse_catalog


html = Path("sample_catalog.html").read_text(
    encoding="utf-8"
)

courses = parse_catalog(html)

print(f"Found {len(courses)} courses.")

for course in courses:
    print(course)