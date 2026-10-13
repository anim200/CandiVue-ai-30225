"""Live transcript service (F4): the transcriber container.

It joins every live interview as a hidden, listen-only participant, sends
each person's audio to Deepgram (speech-to-text) and saves the transcript
as speaker-attributed, timestamped turns (transcript_turns). The room page
reads them through GET /api/interviews/{id}/transcript.
"""
