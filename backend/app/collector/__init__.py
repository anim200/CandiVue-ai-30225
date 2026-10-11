"""CV Collector service (Figure 2, step 7; §4B-9).

Applicants upload their CV in the Google Form linked in the job post. Google
saves the file in Drive and the answers in the form's response Sheet. This
service reads new responses, downloads each CV into the CV intake folder
and records the candidate. It runs in its own container ("cv-collector"):
only that container holds the Google key, and it can only read.
"""
