# BioDetective AI

**Evidence-grounded causal intelligence for biological claims.**

BioDetective is a Python web application for asking biology questions and investigating biological claims in a clean, ChatGPT-inspired research workspace. Gemini handles language generation and voice transcription. Chat and claim searches retrieve candidate papers from Europe PMC / PubMed, OpenAlex, and Crossref.

The claim workflow is:

> Claim → entities and relationships → competing hypotheses → literature retrieval → evidence cards → pilot BES → weakest link → next validation

## Run the web app

Use Python 3.10 or newer. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then store it in the ignored `.env.local` file. The server keeps the key private and never sends it to the browser.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

`python` must point to Python 3.10 or newer. Starting the app opens [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. The server listens on the local computer by default. Internet access is required for AI responses, speech transcription, scholarly search, and literature retrieval. A saved key does not guarantee quota or model access; the app displays Gemini usage-limit and access errors from the project.

Add the following to `.env.local` and replace the blank key value with the key from AI Studio:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.8-flash
```

Keep `.env.local` private and out of source control. The default model, Gemini 3.8 Flash, is listed with a no-cost API tier, but Google applies changing rate and usage quotas; it is not unlimited. Google AI Studio's free tier may use prompts, files, and audio sent to the model to improve products. Do not submit confidential or unpublished material on that tier. Paid projects can incur model charges. Check the current [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [API terms](https://ai.google.dev/gemini-api/terms) before selecting a project. The app settings let you select Gemini 3.8 Flash, Gemini 3.5 Flash, or Gemini 3.1 Flash-Lite, choose reasoning depth and chat response style, enable or disable scholarly source search in chat, and save personal instructions. These preferences stay in browser storage. The optional `GEMINI_MODEL` environment setting controls the default model.

## What it does

- Chat about biology with scholarly literature retrieval and source links.
- Investigate causal claims by decomposing the claim and proposing competing hypotheses.
- Retrieve candidate publications across Europe PMC / PubMed, OpenAlex, and Crossref.
- Extract source-linked support, contradiction, study design, model, intervention, and limitations from available abstracts.
- Show relationship-level evidence, a weakest link, uncertainty, and a suggested next validation.
- Calculate a transparent, uncalibrated pilot Biological Evidence Score (BES).
- Attach PDF, DOCX, TXT, Markdown, and CSV files for text review.
- Record a voice question in a supported browser, transcribe it online, and place the text in the composer for review.
- Switch between light and dark appearance. Chat history is stored in this browser.

## Privacy and scientific limits

Messages, extracted text from attached documents, and microphone recordings selected for transcription are sent to Gemini for processing. On Google's no-cost API tier, submitted content may be used to improve Google products; avoid confidential or unpublished material. File contents and audio recordings are not stored by BioDetective. Public literature search terms are sent to the named scholarly services. Conversation history stays in browser local storage.

Search coverage is not exhaustive. Retrieved records are candidates, not proof. Automated classifications can misread abstracts and require expert review. BES is an uncalibrated weighted share among retrieved classified records; it is not a truth probability or a validated scientific measure. BioDetective does not replace expert judgment or provide clinical advice. See the [scientific specification](docs/BIODETECTIVE_SCIENTIFIC_SPEC.md).

## Architecture

- Python 3 + FastAPI serves the application and keeps the API key server-side.
- Google Gemini API powers biology chat, structured claim analysis, evidence extraction, and voice transcription.
- Europe PMC / PubMed, OpenAlex, and Crossref provide biomedical publication records and abstracts.
- Browser JavaScript handles chat history, theme switching, attachments, and microphone capture.

BioDetective is an application and research workflow built around hosted AI models; it does not claim to train a foundation model from scratch. The old Windows desktop entry point is no longer used by `main.py`.

