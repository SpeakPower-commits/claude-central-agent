<div align="center">

<img src="../docs/speakpower-logo.png" alt="SpeakPower" width="120" />

# SpeakPower Studio

**Give it a recording. Get back shorts, a cleaned episode, and the text.**

</div>

---

## What this is

You paste a link to a video. GitHub does the work on its own computers. You
come back and download the finished clips.

**Nothing is installed on your computer.** It all happens in a web browser, so
it works on a locked-down office desktop.

**Your video is never uploaded from your desk.** You give it a link — a Google
Drive or YouTube address — and GitHub's machine fetches the file directly. Your
office internet is never used to move a two-gigabyte file.

### What comes back

| | |
|:--|:--|
| **Vertical shorts** | 1080×1920 with captions burned in, ready for Reels, TikTok and YouTube Shorts |
| **Cleaned episode** | the full recording with dead air cut out and sound levelled to broadcast standard *(optional — it's slow and big)* |
| **Transcript & captions** | a readable transcript, plus a `.srt` subtitle file you can upload to YouTube |
| **Written assets** | show notes, a blog outline, and ready-to-post captions |

---

## Setting it up — once, about ten minutes

### 1. Add your Claude key

In this repository on github.com:

**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

- Name: `ANTHROPIC_API_KEY`
- Value: your key from https://console.anthropic.com

This is the only required step. The key is encrypted and never visible in the
code or the logs.

### 2. Optional, but strongly recommended: a Deepgram key

Without this, the speech-to-text runs on GitHub's processor and is **slow** —
around 30–40 minutes for a one-hour recording. With it, the same hour takes
about two minutes and costs roughly **$0.25**.

Sign up at https://deepgram.com (they give $200 of free credit), then add a
second secret:

- Name: `DEEPGRAM_API_KEY`
- Value: your Deepgram key

Deepgram's `nova-3` model also handles accented English noticeably better,
which matters for East African voices.

---

## Using it — every time

### 1. Put the video somewhere with a link

Google Drive is easiest. Upload the file, then **Share** → change to
**"Anyone with the link"** → **Copy link**.

> If it stays set to "Restricted", the fetch will fail and tell you so.

An unlisted YouTube video works too, as does Dropbox.

### 2. Start the job

Go to the **Actions** tab at the top of this repository → click
**"Studio — edit a recording"** on the left → click the **Run workflow**
button on the right.

Fill in the small form:

| Field | What to put |
|:--|:--|
| **Link to the recording** | the Drive or YouTube link you just copied |
| **What is this?** | a sentence of context, e.g. *"Interview with a church media director about donor communication"* — this genuinely improves which moments get chosen |
| **How many shorts** | 8 is a sensible default |
| **Framing** | `blur` keeps the whole picture (safe for two people on screen); `crop` fills the screen but can cut off someone standing off-centre |
| **Also produce the cleaned full episode** | leave off unless you need it — it roughly triples the time |

Click the green **Run workflow**.

### 3. Collect the results

The job appears in the list. Click into it to watch progress in plain English
("Listening to the audio", "Cutting the shorts").

When it finishes, scroll to the bottom of that page. Under **Artifacts** you'll
find **studio-shorts** — a zip containing the clips, the thumbnails, the
transcript and the written assets. There's also a summary at the top of the
page listing every clip and why it was chosen.

**Roughly how long:** a one-hour recording takes about 10 minutes with a
Deepgram key, 40–50 minutes without one. Add 30–60 minutes if you asked for the
cleaned episode.

---

## What it costs

| | |
|:--|:--|
| GitHub Actions | **Free** — 2,000 minutes/month on a private repository |
| Claude (choosing the moments) | about **$0.10–0.30** per recording |
| Deepgram (optional) | about **$0.25** per hour of audio |

So roughly **50 cents a video**, and nothing at all if you run out of patience
rather than money.

If you exceed the free GitHub minutes, the workflow simply stops running until
the next month, or you add a payment method.

---

## When something goes wrong

| What you see | What it means |
|:--|:--|
| *"That link is private"* | The Drive sharing is still Restricted. Set it to "Anyone with the link". |
| *"That file has no audio track"* | The upload lost its sound, or it is a silent screen recording. |
| *"ANTHROPIC_API_KEY is not set"* | Step 1 above was missed, or the secret is named differently. |
| *"none survived checking"* | The editor proposed clips with bad timecodes. Run it again — this is usually a one-off. |
| *"No clips were found"* | The recording genuinely has no self-contained moment in it. Short or rambling material does this. |

Every failure is written in plain language at the end of the log and on the run
summary.

---

## Tuning it

Under **Settings → Secrets and variables → Actions → Variables** you can set:

- `STUDIO_MODEL` — defaults to `claude-sonnet-5-5`. Set it to `claude-opus-5`
  for a piece worth the extra judgement; it costs more and picks better.
- `STUDIO_WHISPER_MODEL` — `small` by default. `medium` is more accurate on
  accented or noisy audio, and about three times slower. Only matters when you
  are not using Deepgram.

---

## How it works, briefly

```
link → fetch → transcribe → Claude picks the moments → render → download
```

The only part that is genuinely AI is the third step. Cutting video is
mechanical; deciding *what* to cut out of an hour of talking is the work a
client is paying for.

| File | What it does |
|:--|:--|
| `core/fetch.py` | pulls the video from a shareable link |
| `core/transcribe.py` | speech to timed text (Deepgram or local) |
| `core/analyse.py` | asks Claude for the clips and the written assets |
| `core/media.py` | all ffmpeg work: dead air, loudness, vertical framing, captions |
| `core/pipeline.py` | runs the stages in order and records progress |
| `run.py` | the command the workflow calls |

---

## Known limits

- **Link only.** There is no drag-and-drop upload, because GitHub has no upload
  box. Everything has to come from a shareable link.
- **The cleaned episode is a big download** and is uploaded as a separate
  artifact so a large file can never stop you getting the clips.
- **Long captions can fill the frame.** Where a speaker runs on without
  pausing, the caption block gets tall. Deepgram splits more sensibly than the
  local model does.
- **No multi-camera switching yet.** That needs separate synced camera files,
  and depends on how your shoots are actually recorded.

---

## Running it on a computer instead

Everything here also runs as a normal command, if you ever get a machine you
control. You need Python 3.11 and ffmpeg installed, then:

```bash
cd studio
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python3 run.py --source "https://drive.google.com/..." \
               --context "Interview with a church media director" \
               --out ./outputs
```

`--source` also accepts a path to a local file, which skips the fetch entirely.

---

<div align="center">
<sub>A product of <strong>SpeakPower</strong></sub>
</div>
