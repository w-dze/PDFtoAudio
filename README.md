# PDF to Audio

A small local web app that lets you upload a PDF and start text-to-speech playback. 

This app is meant to run on your own computer. 

## Features

- Upload or drag in a PDF from the browser
- Start PDF text-to-speech playback
- Stop playback
- Runs locally at `http://127.0.0.1:8000`

## Requirements

- Python 3
- `pip`

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Run Locally

Start the local server:

```bash
python3 main.py
```

Open this URL in your browser:

```text
http://127.0.0.1:8000
```

## How To Use

1. Choose or drag a PDF into the upload area.
2. Click `Upload PDF`.
3. Click `Start` to begin listening.
4. Click `Stop` to pause playback.

## Notes

- Uploaded PDFs are saved in the local `uploads/` folder while the app runs.
- `.venv/`, `__pycache__/`, and `uploads/` should stay out of Git.
- Some scanned PDFs may not work well because they contain images instead of selectable text.

## Stop The Server

In the terminal where the server is running, press:

```bash
Ctrl+C
```
