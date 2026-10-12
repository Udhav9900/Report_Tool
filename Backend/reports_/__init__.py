"""Sonar report builder: results + test details -> Sonar-branded .docx report."""
from .render import generate_report

__all__ = ["generate_report"]