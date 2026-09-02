# Baseline review

A generated real-workbook baseline starts as `candidate`. Review means confirming that the observed sheets, block detection and warnings match the intended import behavior for that exact source revision. Only then may `review_status` be changed to `approved`; unexplained drift must never be accepted merely to make CI green.
