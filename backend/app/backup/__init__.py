"""Operator site backup tool.

python -m app.backup                    run the daily schedule (Compose `backup` service)
python -m app.backup once               create one backup now
python -m app.backup check ARCHIVE      verify an archive without changing anything
python -m app.backup restore ARCHIVE [--replace]
"""
