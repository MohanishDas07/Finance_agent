# Interview Prep: AI Judge Dossier
 
## Architectural Mandate & Design Philosophy
This system strictly follows the design mandate: **deterministic reasoning where possible, AI only where necessary**.
- **Deterministic Core**: The core arithmetic, 90-day cash flow simulation, recurrence detection, and plan selection are 100% deterministic code.
- **AI Extensions**: AI/LLMs are reserved specifically for processing unstructured inputs (\messages.csv\ and \images.csv\) to extract discrete financial facts (e.g., salary increases) and for generating the final human-readable \decision_explanation\.
 
## Key Technical Decisions & Trade-offs
1. **Recurrence Detection**: 
   - We implemented a hybrid grouping strategy to detect cadences.
   - We project 'fixed' flexibility expenses using the exact amount of the latest event, while variable/flexible expenses project the historical *maximum* to remain maximally conservative.
   - We introduced a strict **liveliness check**: If a recurrence hasn't occurred within its expected timebound relative to the request date, it is classified as 'dead' and is not projected.
 
2. **Pending Transactions & Date Snapping**:
   - We realized \current_available_balance\ *already* holds pending past debits. We strictly filter out pending debits from being deducted a second time if their \vent_date\ is before the equest_date\, preventing artificial deflation of the baseline balance.
 
3. **Plan Selection Hierarchy**:
   - The engine simulates affordability up to the \desired_completion_date\. If a user cannot afford a full payment on the request date, the system iterates through options (partial payments, installments) guided by the user's \minimum_balance_to_keep\ and \max_installment_months\.
 
## Edge Cases Resolved
- **Lump Sum vs. Recurrent Overlap**: Prevented one-off large purchases within a category from destroying the true underlying recurrence by isolating strict date differentials (max-min diff variance < 5 days).
- **Salary Adjustments**: Built an \EvidenceExtractor\ to parse unstructured message amendments. For a user, a message dictates a salary increase on 08-15, which the system seamlessly wires into the ledger before projection.
 
## Evaluation Notes
The pipeline is fully terminal-runnable (\python code/main.py\), outputs exactly one row per request, and maintains comprehensive logging in \log.txt\.
