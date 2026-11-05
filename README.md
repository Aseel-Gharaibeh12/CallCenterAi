# CallCenterAi

Voice customer-service assistant for **Al-Mustaqbal Public Safety** (fictional company, for learning).
Built with [Pipecat](https://github.com/pipecat-ai/pipecat) and free Groq models (speech-to-text, LLM, text-to-speech), with a custom Arabic/English web interface.

## Run (macOS)

1. Get a free API key at https://console.groq.com/keys
2. Run:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```
3. Paste your Groq key when asked (it is saved locally in `.env`, which is not uploaded).
4. Open http://localhost:7860/app/ in Chrome, allow the microphone and click "Start conversation".

## Files

- `bot.py` – the voice bot pipeline
- `company_info.txt` – company information the assistant answers from
- `ui/index.html` – the web interface
- `run.sh` – installs everything and starts the bot

## Run on a server (Docker)

See [DEPLOY.md](DEPLOY.md) for step-by-step instructions (Arabic) to run the assistant 24/7 on a Linux server with HTTPS.
