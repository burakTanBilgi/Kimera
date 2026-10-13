# The Riddle Moth

The first job Kirpi's model did for us. 2026-10-01.

A small riddle game in the browser. A moth gives a riddle, you guess the word,
you can ask for a hint. The page was written by the model on Kirpi, and the
riddles and hints are written by the same model while you play.

## The experiment

A separate Claude chat (Sonnet) was given `BRIEF.md` and told: the model on
Kirpi does the work, you only write instructions and check the result, and you
spend as few of your own tokens as you can. Claude never read the model's files
into its own context. It checked them with `node --check`, `wc`, `grep` and one
screenshot.

## What happened

| Call | Instruction | Result | Model wrote | Time |
|---|---|---|---|---|
| 1 | `prompts/p1.txt` | `game/index.html` | 219 tokens | 40 s |
| 2 | `prompts/p2.txt` | `game/style.css` | 911 tokens | 160 s |
| 3 | `prompts/p3.txt` | `game/game.js` | 716 tokens | 135 s |
| 4 | `prompts/p4.txt` | `game.js` again, a repair | 725 tokens | 144 s |
| 5 | `prompts/p5.txt` | `style.css` again, a repair | 789 tokens | 146 s |

- The model: 5 calls, read 2,049 tokens, wrote 3,360 tokens, 625 seconds of
  work. That is 5.4 tokens a second.
- Claude's instructions: five files, 7.1 KB together, about 1,800 tokens.
- Fixed by hand: one line. The model wrote `solved++` twice in the repair.
- Missed by the model: "Enter in the box also checks the guess" was asked for
  and is not in the code. One unused variable is left in `newRiddle`.
- Claude's total tokens: **not recorded.** The chat was started from inside
  another Claude session, so it ran as a child and saved no transcript, and
  `tools/tokens` read the parent's transcript instead. Next time start the chat
  with `env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION -u CLAUDECODE`.

## What this says about the model

Qwen3.5 4B on Kirpi, at about 6 tokens a second:

- It writes a small, complete file from a precise instruction, first try, when
  the instruction names every id, function and sentence.
- It needs the instruction to be that precise. It does not design.
- A file of about 900 tokens is the comfortable size: two and a half minutes.
- It drops one detail in ten and can repeat a line. Someone has to check.
- Short creative answers are its best use here: a riddle is 30 tokens, 5 seconds.

## Play it

Kirpi must be on. Then, on Tilki:

```sh
KIRPI_SSH_HOST=USER@HOST tools/kirpi-tunnel          # Tilki 127.0.0.1:8081 -> Kirpi's model
cd game && python3 -m http.server 8090 --bind 127.0.0.1
```

Open `http://127.0.0.1:8090`. Both ends are on 127.0.0.1. Nothing is opened to
the network.

## Files

- `BRIEF.md`: what the chat was told.
- `prompts/`: every instruction Claude wrote.
- `game/`: the game as served.
- `out/`: the model's repairs before they were copied in, and one screenshot.
- `qwen-log.jsonl`: one line per call, with tokens and seconds.
- `tools/kirpi-tunnel`, `tools/kirpi-ask`, `tools/tokens`.
