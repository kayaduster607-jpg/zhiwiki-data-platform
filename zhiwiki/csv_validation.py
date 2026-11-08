"""Shared bounded CSV parsing and safe field-limit classification."""

import csv
import io
import re


class CsvFieldTooLarge(ValueError):
    """A field exceeded the interpreter's current CSV parser limit."""

    def __init__(self, limit):
        self.limit = limit
        super().__init__("CSV 单字段超过 {} 字符限制".format(limit))


def csv_rows(text):
    """Yield parsed rows without changing Python's process-wide CSV limit."""
    try:
        yield from csv.reader(io.StringIO(text, newline=""), strict=True)
    except csv.Error as error:
        # CPython reports the limit as a number only; never copy field content.
        match = re.fullmatch(r"field larger than field limit \((\d+)\)", str(error))
        if match:
            raise CsvFieldTooLarge(int(match.group(1))) from None
        raise
