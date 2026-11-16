# Workbook Analysis & Verification Record

## 1. Source Workbook Examination
Analysis of the department's Excel workbook (e.g. `int-I`, `int-II`, `Model revised 2.0` sheets):
- **Internal Exams**: Continuous Assessment Tests covering designated subsets of COs (e.g. CO1, CO2, CO3).
- **Model Exams**: Comprehensive exam covering all Course Outcomes (CO1 to CO5).

## 2. Attainment Formula Verification
- Formula in workbook: `=IF(CO_Percentage > Pass_Percentage, 1, 0)`.
- Evaluated strictly with numeric 1 or 0.
- Student percentage computed from dynamically aggregated question scores.

## 3. Identified Structural Discrepancy
- Historical sheet `Model revised 2.0` lists question columns Q1 through Q20.
- Confirmed requirement states 15 questions (10 x 2m + 5 x 8m = 60m).
- Both structures are supported transparently by the dynamic calculation engine and database schemas.
