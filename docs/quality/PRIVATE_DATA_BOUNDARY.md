# Private data boundary

Real scientific workbooks used for normative QA are test inputs, not repository assets. Public Git history may contain case metadata and filenames needed to select the correct input, but must not contain raw workbook bytes or generated private baselines. This boundary prevents unpublished analytical data from being published accidentally while preserving reproducible QA contracts.
