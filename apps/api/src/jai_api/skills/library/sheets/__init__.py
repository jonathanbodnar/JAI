"""Google Sheets skills — tab-aware row reading.

The existing `drive.read_doc` only exports the first tab of a
spreadsheet as CSV. Real workflows ("read New Creator Links from
my outreach sheet") need to target a specific tab and get rows back
as structured data, which is what these skills provide via the
Sheets API.
"""
