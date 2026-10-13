# Changelog

Versions follow SemVer. Before 1.0 the minor number counts a shipped road or limb and a patch is a fix.
This is the public history; it leaves out changes to the private parts.

## 0.9.1 (2026-10-13)

- The working class is checked on the real machine end to end: the start parked the large model and kept search ready, a wake during the chat was answered queued, the chat named its machine and limit, edited a file and ran a command, its diff came back, and after the chat ended the model loaded by itself in 5 s.

## 0.9.0 (2026-10-13)

- A working class on the 4 GB machine: a start in a mode that can write takes a lease from the job switch, which parks the large model (the small search model stays up) and gives the chat an 1800 MB box. The model's work waits and is owed a turn: a `wake` during the chat is answered `queued`, and the model loads by itself when the chat ends. Nothing is killed while nobody waits; with someone waiting, the chat is stopped at 120 minutes and can be resumed.
- `sample` says what a device takes now: `none`, `light` or `working`.
- Each chat is told what machine it is on, its memory limit, how its work goes back, and how to work to that size.
- Not yet checked on the real machine end to end.

## 0.8.5 (2026-10-13)

- Found by review of 0.8.4: the added folders go at the end of a chat's PATH, not the start, so a program dropped there by one chat cannot stand in for `git` or `sh` in later chats.

## 0.8.4 (2026-10-13)

- The user's Rust tools (`~/.cargo/bin`, when it exists) are on a seat chat's PATH; a chat started over ssh does not get what a login shell has.

## 0.8.3 (2026-10-13)

Found by review of 0.8.2.

- The device itself refuses work that carries `.memory`: the check is made by the program that unpacks, not only by the one that sends.
- The pack is reached by folder handle from its root down, one step at a time.

## 0.8.2 (2026-10-13)

Found by review of 0.8.1.

- A pack is walked by folder handle, never by path, so swapping part of the path for a link during the read cannot lead out of it.
- The reserved folder name is checked in any spelling.

## 0.8.1 (2026-10-13)

Found by review of 0.8.0.

- Work that carries its own `.memory/` folder is refused, so a commit cannot plant "memory" for the next chat.
- A pack file is opened without following a link and judged by what was opened.
- A seed with a pack has a working time limit.

## 0.8.0 (2026-10-13)

- `seed` takes an optional pack: a plain folder of text files laid read-only at `.memory/` in the seat folder, in place before the chat starts and never reported by `fetch`. Text only, no links, 2,000 files, 20 MB.

## 0.7.0 (2026-10-13)

- The 4 GB machine's transcripts are mirrored too. It has no rsync package, so the mirror key's forced command is `kimera-rrsync`, a small wrapper that serves the folder read-only with an rsync unpacked in the home folder.

## 0.6.5 (2026-10-13)

Found by review of 0.6.4.

- `fetch` also refuses every code point Unicode calls ignorable by default (fillers, joiners, all variation selectors, tags), the blank braille cell, and any space that is not the plain one.
- Known limit: this is not a look-alike filter. A diff is untrusted text and is reviewed as such by whoever applies it.

## 0.6.4 (2026-10-13)

Found by review of 0.6.3.

- `fetch` decides hidden text by Unicode category, not by a list: any control, format, private-use or unassigned character, a line separator, or a picture-less variation selector in the diff is refused. Ordinary non-English text and plain emoji pass.
- `seed` reads the tar one entry at a time, counted as it reads, under a memory limit for that process.

## 0.6.3 (2026-10-13)

Found by review of 0.6.2, all in `fetch`.

- A fetch that was refused or cut short no longer blocks the next one: every fetch starts from what was seeded, and a leftover lock is removed.
- A diff holding a Unicode direction mark, a line separator, a zero-width space, a byte-order mark or a lone carriage return is refused, because such text reads differently from what it is.

## 0.6.2 (2026-10-13)

Found by review of 0.6.1, all in `fetch`.

- A diff holding ESC or another control character is refused; it could drive the terminal of whoever reads it.
- A file name that is not UTF-8 no longer slips past the size limit: names are handled as bytes.
- A file that grows after it was measured cannot fill the disk: git takes the changes in under a file-size limit.

## 0.6.1 (2026-10-13)

Found by review of 0.6.0, all in `fetch`.

- A file name can no longer forge a line of the log or of an answer.
- Bounds come before the work: changed and new files are measured first and only then taken in, and every git output is read up to a cap.
- A chat's own `.gitattributes` cannot pass a binary file off as text: attributes are read from what was seeded, and the diff is checked again for a NUL byte and valid UTF-8.

## 0.6.0 (2026-10-13)

- `fetch`, the twelfth verb: what a chat changed in a seeded folder since the seed, as one text diff (2 MB at most). A link or a binary file is refused by name, and what the work itself ignores is left out. The record of what was seeded is a git repository kept outside the seat folder; git runs with no hooks, no outside diff program and none of the user's configuration. The caller applies the diff itself; nothing in it is run.
- Found by review of 0.5.0: a device that takes no chats now refuses work as well; seeded work may not push free disk under the device's floor; a seed is refused under or above a folder a chat runs in; a link planted where the new folder is built is removed, never followed.

## 0.5.0 (2026-10-13)

- `seed`, the eleventh verb: a read copy of a git worktree (tracked files at HEAD only) is put in the seat folder on the device. The work streams from git and is spooled to disk on the device. Only plain files and folders are taken; a path that leaves the folder, more than 20,000 files or 200 MB, the seat root itself, or a folder a chat runs in is refused. The new folder is built beside the old one and swapped in.
- A device without Node can use an unpacked one, first on the PATH of seat chats only.
- A chat no longer updates the agent program under itself; an update that landed during a chat had broken its search tools.

## 0.4.0 (2026-10-13)

- The public part: this repository, built from an allowlist by a script that refuses to produce anything unless the tests pass inside the tree and a scan finds no address, user, host or mail address.
- Files shown here no longer hold a user or host: the real-machine test and the experiment's tunnel take them from the environment.
- The log behind "5.4 tokens a second" is in the repository.

## 0.3.1 (2026-10-13)

- `kimera-perf` fails closed. Any surprise now writes `unknown` as the device's latest reading; before, the program stopped and an old `up` stayed in the file. Found by review of 0.3.0.

## 0.3.0 (2026-10-13)

- The latest reading of each device is kept in a file other programs may read, so a viewer never calls a device. It is the reading already taken every minute; no extra call is made.

## 0.2.1 to 0.2.5 (2026-10-13)

Fixes found by review of the release before each.

- A device can narrow the tools a chat is given, whatever was asked for.
- The private tmux on a device without the package is a fixed path checked by its sha256, and no library path comes from a file a chat can write.
- `authorize-device.sh` can add only the keys that are named, and never leaves a weaker line for a key it did not add. A line is kept only if it is exactly the line it would write.

## 0.2.0 (2026-10-13)

- The 4 GB machine takes one read-only chat: plan mode only, in a 500 MB memory box, when 650 MB is free. The local model keeps the rest.
- New per-device settings: allowed modes, a memory box, a private tmux.
- `sample` answers for every device.

## 0.1.1 to 0.1.3 (2026-10-13)

Fixes found by review of the release before each.

- No MCP server of any scope loads in a device chat, and the empty configuration is passed inline, not as a file a chat can write.
- An unreadable user settings file refuses the start; it was read as empty.
- A seat settings file that drifted from its pristine copy is restored with a line in the log.
- The read-only agent takes its prompt on stdin, so a prompt cannot become an option.

## 0.1.0 (2026-10-13)

The first tagged release.

- The seat road: `kimera-run DEVICE VERB` over a key limited to one command, to `kimera-seat` on the device. Ten verbs, admission on the device, one lock per device, a log line per verb, shapes checked on both ends.
- The transcript mirror (staged, bounded, read-only) and the hooks forward (one loopback port, a token per device).
- The performance record: one line per minute while a chat runs.
- The job switch for the local model: leases, on-demand parking, a timer that puts things right.
