"""Spreadsheet-safe CSV responses for immutable account records."""

import csv
import io

from fastapi import Response


def csv_response(headers, rows, filename):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    for values in rows:
        writer.writerow(
            [
                "'" + str(v)
                if str(v).startswith(("=", "+", "-", "@", "\t", "\r"))
                else v
                for v in values
            ]
        )
    return Response(
        "\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
