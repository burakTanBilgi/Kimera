# Brief: let Kirpi's model build a small creative game. You only give instructions.

Written 2026-10-01 by the Kimera session for a separate Claude Code chat. Tan is watching.

## The experiment
Tan wants to see what the small local model on Kirpi can really do, and how few Claude tokens it
takes to direct it. **The model does the work. You only write instructions and check results.**
Your score is your own token count: lower is better. At the end, report it.

Goal: **a small creative game that runs on localhost on this laptop (Tilki), written by the model.**
Which game is up to you and the model. It should show the model's strengths, so the best games also
call the model while being played (a story, a riddle keeper, a creature that answers), not only once
to write the code. Small and working beats ambitious and broken.

## What you are working with
- **Kirpi**: an old Lenovo, 3.6 GB of memory, no graphics card. It runs **Qwen3.5 4B** (4-bit) under
  llama.cpp. About **5.8 tokens a second**. Its whole window is **4096 tokens**, prompt and answer
  together. So: one small file per request, each answer under about 1500 tokens (about 4 minutes).
- It is reached from here at **http://127.0.0.1:8081** (OpenAI-style `/v1/chat/completions`), through
  an SSH tunnel. If it stops answering, run `tools/kirpi-tunnel`.
- The browser may call that address directly from a page served on 127.0.0.1 (CORS allows it).
  For play-time calls keep `max_tokens` small (60 to 120) and send
  `"chat_template_kwargs": {"enable_thinking": false}`, or every turn takes minutes.

## Your tools (in `tools/`)
- `tools/kirpi-ask PROMPT_FILE OUT_FILE [--max N] [--code]`: sends your instruction, saves the model's
  answer to a file, prints **one line** (tokens, seconds, size). `--code` keeps only the code block.
- `tools/tokens`: prints what you (Claude) and the model have spent so far. Run it at the end.

## How to spend few tokens
- **Do not read the model's files into your context.** Check them with commands that print little:
  `node --check file.js`, `python3 -m py_compile`, `grep -c`, `wc -c`, `head -c 200`.
- When something is broken, send the error text back to the model with the file and let it fix it.
  Fix by hand only as a last resort, and count it in your report.
- Write instructions for a small model: one job per request, say the exact file, the exact names of
  functions and ids it must use, and "answer with one code block only".
- No subagents. No long explanations to Tan while working.

## Rules
- Serve the game with `python3 -m http.server 8090 --bind 127.0.0.1` from the `game/` folder.
  **127.0.0.1 only**, never 0.0.0.0.
- Do not log in to Kirpi, do not change anything on it, no sudo anywhere. Only talk to the model.
- Stay inside this folder (`experiments/qwen-game`).
- Tan steers by seeing: plain words, short answers.

## When it runs
Tell Tan, in a few lines: the address to open, what the game is, what the model wrote and what you had
to fix by hand, and the two lines from `tools/tokens`. Then stop.
