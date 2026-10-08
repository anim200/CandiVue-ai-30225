"""CV screening and scoring (F1, F2): the parts LangGraph 2 is built from.

Everything here runs locally (no Gemini): text extraction and OCR, rule-based
parsing, semantic matching with the local embedding model, and rule-based
scores. The scoring weights come from the interviewer, or else from the
Hiring Assistant's suggestion, or else from fixed defaults.
"""
