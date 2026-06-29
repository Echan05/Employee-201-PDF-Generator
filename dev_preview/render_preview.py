"""
Renders the template with sample data and produces output.html + output.pdf
for visual inspection. Run from the project root: python dev_preview\\render_preview.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jinja2 import Environment, FileSystemLoader
from dev_preview.sample_data import build_sample_data
from app.services.template_context import build_template_context

env = Environment(loader=FileSystemLoader("app/templates"))
template = env.get_template("employee_201.html")

data = build_sample_data()
context = build_template_context(data)
html = template.render(**context)

os.makedirs("dev_preview", exist_ok=True)
with open("dev_preview/output.html", "w", encoding="utf-8") as f:
    f.write(html)

print("HTML written to dev_preview/output.html - open it in a browser to check layout first.")

try:
    from weasyprint import HTML
    HTML(filename="dev_preview/output.html").write_pdf("dev_preview/output.pdf")
    print("PDF written to dev_preview/output.pdf")
except ImportError:
    print("WeasyPrint not installed yet - run: pip install weasyprint")