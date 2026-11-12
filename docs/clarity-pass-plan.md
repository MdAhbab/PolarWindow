# PolarWindow: plan for the clarity pass

Status on 13 November: Parts A to H are built (see `handoff.md` section 7). Part I, the final design
check, is still to do (see `handoff.md` section 8.6).

Written 12 November 2026. This plan covers the requests from your last message. It adds to the design
rounds already planned (rounds 3 to 7) and says where each new piece fits.

## 1. What you asked for

1. Show on the Missions list what each mission has, so nobody opens a mission and finds it empty.
2. Every mission has something worked out on every step, using assumed values where nothing is published.
3. Make it obvious that the turning sky view turns. Do the same for every other hidden feature.
4. The best features are direct: one tap away, in plain short words.
5. No hard words, no long sentences, no long dashes, no AI model names on screen.
6. Details (sources, dates, methods) are tidy and out of the way, but there when wanted.
7. People know where they are, what to do next and how the app flows. Very little to learn.
8. More pictures and marks, fewer numbers and sentences.
9. The Ask bar and the "how the AI got this" panel stop looking generic.
10. A final design check after all the work.

## 2. What the app does today (checked on the running app)

| Fact | Detail |
|---|---|
| Missions in the list | 20: 4 flown, 15 planned, 1 cancelled. Plus your 2 projects. |
| Planned missions with no landing date published | 9 of 15 |
| Planned missions with no landing site published | 11 of 15 |
| What a planned mission's steps say | Ready: "needs input". Launch, Trip and the rest: "not published" or "not worked out". |
| What already exists but is hidden | Each planned mission already has up to three worked examples built from past flights (checked on CS-8: Launch, Trip, Landing, Contact and Return are worked out). They sit behind a small "Explore a scenario" link. |
| What the worked examples lack | The Surface step: no site and no dates are assumed, so sunlight and contact are missing. |
| The turning view | The 3D sky view on the Skyline page. Its only hint is "Drag to look around" at the end of a long caption. |
| The AI label | Every answer shows "AI answer · gemini-3.8-flash · 3.2 s". |
| The Ask bar | A plain text field with the same placeholder on every page. |

So the main problem is not missing work. The app hides what it has, and shows "not published" first.

## 3. The plan

### Part A. The Missions list shows what is inside each mission

Each row gets a strip of six marks, one per step, in the order of the journey:

```
Blue Ghost Mission 3                                        Planned
Firefly Aerospace · landing date not published
Geology · Imaging · Rover · 3 more

Ready ○   Launch ▨   Trip ▨   Surface ▨   Contact ▨   Return ▨
```

One legend sits above the list, always visible:

| Mark | Meaning |
|---|---|
| ● solid | From the mission's own record (published or flown) |
| ▨ hatched | Worked example: worked out from assumed values |
| ○ hollow | Needs your input |

- The marks are shapes, not red, amber and green. The app's rule stays: no traffic lights, no score.
- The hatch is the same hatch the app already uses for assumed values, so it means one thing everywhere.
- Each mark is a link: tapping "Surface" opens that step of that mission.
- A filter above the list: "Full record", "Worked example", "Needs input".
- The same strip appears on the Home cards and at the top of each mission page (it reuses the step line
  planned in round 4).
- The words "Unconfirmed" and "Payloads unconfirmed" become "not published yet".
- The payload list becomes at most three small icon chips and "3 more".

Work: the server adds each mission's six step states to the list it already sends (one new field), so the
page needs no extra requests.

### Part B. Every mission opens with something worked out

1. **Show the worked example first.** A planned mission with gaps opens on its first worked example, not
   on empty steps. One line at the top says so: "Worked example, based on past flights. Assumed values
   are hatched." with two actions: "Change the assumed values" and "Show only what is published".
2. **Fill the Surface step.** Extend the worked examples with an assumed landing site and assumed dates,
   so sunlight, contact, the longest night and the longest time without contact are worked out for every
   planned mission.
3. **Where the assumed values come from.** The same rule the app uses now for the rocket and launch pad:
   a named past flight or a published statement. Each assumed value shows its reason, for example
   "Site: Mons Mouton, the target of this provider's last published polar mission". Nothing is made up.
   If no honest reason exists for a value, the step says what is missing and offers one tap to choose it
   (see decision 1).
4. **No dead ends.** Every step that still has nothing shows one sentence and one button that fixes it.
5. **Work them out ahead of time.** All worked examples are worked out on your PC before the site goes
   live, then copied to the server with the database, so no visitor waits.
6. **Flown and cancelled missions do not change.** A flown mission shows its record. The cancelled one
   (APEX 1.0) shows what was published and says it was cancelled.

Rule kept: an assumed value never looks like a fact. Hatch on screen, the word "assumed" in text, and the
AI may only say it as assumed.

### Part C. The sky view, and every hidden feature

The 3D sky view:

- When it first comes into view it makes one slow quarter turn and settles. This shows that it moves.
  Under "reduce motion" it does not turn, and the hint below is enough.
- A "Drag to look around" pill sits on the view with a small hand icon. It fades after the first drag.
- A compass strip (N, E, S, W) under the view slides as the view turns.
- Left and right arrow buttons at the edges, and the arrow keys, turn it too. This also makes it usable
  without a mouse.
- Two direct buttons: "Face the Sun" and "Face Earth". These are the two things people want to find.
- The cursor is a hand over the view. The caption is cut to one short sentence.

Other features people miss today. Each gets a visible cue, using the same small set of cues (a pill hint
that fades after first use, a visible button, or a key hint):

| Feature | Today | Fix |
|---|---|---|
| Play the dates | A small play control on the date bar | Larger "Play" button with a label. One gentle pulse on first visit. |
| What a number means | Tap the label (nothing says so) | A small "?" on each tile |
| Ask from anywhere | `/` or Ctrl+K, known to nobody | A "/" key hint inside the Ask bar |
| Compare by another measure | A dropdown | Buttons, one per measure, the chosen one marked |
| Drop a brief to fill the form | A box on the New project page | Also a "Start from a file" button on Home and Missions |
| Chart hover values | Hover only | A tap shows the same values. A hint on first view. |
| Printable report | A link at the foot of some pages | One "Report" button in the same place on Site, Compare and Plan |

Before building, one agent goes through every page and lists every action that has no visible cue. The
table above is the start of that list, not the end.

### Part D. The Ask bar and the "how it got this" panel

The Ask bar:

- It knows the page. On IM-2 it says "Ask about IM-2". On a site it says "Ask about Connecting Ridge".
- Three suggestion chips under it, written for that page, for example "How long is the longest night
  here?". One tap asks.
- The bar's left end shows a small mark for where you are (the mission's step, or the site's name) so the
  question has a visible subject.
- A "/" key hint at the right end.
- It opens from the bar itself and grows into the answer panel, using the motion already built. It is not
  a separate box that appears elsewhere.

The answer:

- Numbers in the answer are shown as the same tiles the pages use, with their margins. Not buried in a
  paragraph.
- Where the answer is about sunlight or contact, a small day-and-night bar is shown with it.
- Each tile links to the page it came from.
- The top line reads "Answer · 5 numbers checked". No model name, no seconds.

The panel, renamed "How this answer was made", shown as three steps with small icons:

1. **Looked up**: each lookup in plain words, for example "The longest night at Connecting Ridge, 1 to
   30 June", with the number it returned.
2. **Checked**: "Every number in the answer matches a lookup." If one did not, it says the answer was
   replaced by a plain summary.
3. **Written**: the sentence that was produced.

A closed row at the bottom, "Technical details", holds the model name, timing, token counts and tool
names for anyone who wants them. The server-side number check is not touched.

### Part E. Details on demand

One rule for every page: the value, its margin and one small mark for its kind stay on the tile.
Everything else moves behind one tap.

- The four kinds get four small shape marks with one word each: worked out, published, entered, assumed.
  One legend, reachable from every page footer.
- Tapping a tile opens one sheet, "About this number": what it means, where it came from, how it was
  worked out, when, and what was left out. Today these are spread across tags, captions and footnotes.
- Each page has one closed row at the foot, "Sources and method", in place of repeated notes under each
  card. The long footer line on the Missions page (about "≥" and "±") moves there.
- Version stamps, data dates and run identifiers leave the main views. They live in the sheet and in the
  printable report.

### Part F. Words

- Sentences under 20 words. Labels under 5 words. One idea per sentence.
- No em dashes or en dashes anywhere on screen. Ranges use "to".
- No model or vendor names outside "Technical details" and the About page.
- The step pages keep one shape: a question, one sentence, up to four numbers, one picture, one next step.
- A test fails the build if rendered text contains a long dash, a model name, or a word from the banned
  list (best, safest, recommended, score, likely, and the engineer terms already replaced).
- One agent reads every screen out as text and flags any sentence over 20 words. I review the list.

### Part G. Pictures before numbers

Add a picture only where it replaces words. No new colours: amber is the Sun, cyan is Earth, magenta is
over a limit.

| Where | Picture |
|---|---|
| Mission rows and cards | The six-step strip (Part A) |
| The four numbers | A thin day-and-night bar under each number, so "62% in sunlight" is seen as well as read |
| The longest night | A battery outline: the night's length against the battery limit, hatched if the limit is assumed |
| Site cards | A small ring: amber arc for sunlight, cyan arc for contact |
| Payload types | Small icons with a label, in place of a dotted list of words |
| Step pages | One icon per step, the same icon everywhere that step is named |
| Empty states | A simple line drawing and one button, in place of a paragraph |
| Home | "How it works" in three pictures: pick a mission or a site, see the four numbers, try a what-if |

### Part H. Flow: little to learn

- Home opens with three doors, each one sentence: "Follow a mission", "Check a landing site", "Plan my
  own mission". Each leads to a path of three steps.
- One line under the page title always says where you are and what comes next, for example "IM-2, step
  4 of 6: Surface. Next: Contact."
- Every page ends with one main button for the next step.
- The guide stays optional and three steps long (already decided).
- The same control looks and moves the same way everywhere (already built in the motion round).
- Check: an agent runs five first-time tasks from a cold start and counts taps and wrong turns, before
  and after. Tasks: find IM-2's longest night; see what Blue Ghost 3 could face on the surface; turn the
  sky to face Earth; compare two sites; ask a question and see how the answer was made. Target: each in
  three taps or fewer with no wrong turn.
- If you can, hand the app to one person who has never seen it and watch for two minutes. That finds
  more than any script.

### Part I. Final design check

After all parts are in:

1. Full gates on both sides (type checks, unit tests, end-to-end tests).
2. A fresh set of screenshots: every page, wide and phone, light and dark.
3. I review every page against this checklist: one main action; no sentence over 20 words; no long dash;
   no model name; every assumed value hatched; no number without its margin; no step that dead-ends;
   every draggable or playable view has a visible cue; nothing cut or scrolling sideways on a phone; 44 px
   tap targets; readable contrast.
4. The five first-time tasks from Part H, run again.
5. I fix what is left myself or send it back, then update the handoff notes.

## 4. Order of work

Two deadlines shape the order: the long video is due Friday 13 November at 6:30 PM, and the project page
on Saturday 14 November. The site stays live through global judging, so later work still counts.

| When | Work | Who |
|---|---|---|
| Now | Round 2 finishes (true numbers, no "best"; phone fixes). I gate and commit it. | running |
| First, before recording the video | Part A (list strip and legend). Part B steps 1, 4 and 6 (show the worked example first). Part C sky view. Part F model names off the screen. | 1 Opus: server field, mission pages. 1 Sonnet: list strip, sky view. |
| Second, before Saturday's submit | Part B steps 2, 3 and 5 (Surface in worked examples, worked out ahead). Part D (Ask bar and answer panel; this replaces the Ask part of round 5). Part E. | 1 Opus: worked examples, Ask. 1 Sonnet: details sheet, tile marks. |
| Third, during judging weeks | Part G pictures. Part H flow. Rest of Part C. Rest of rounds 3 to 6 not already covered. | 1 Opus, 1 Sonnet per round |
| Last | Part F sweep and tests. Part I final check. Round 7 cleanup. | Sonnet sweep, then my review |

How this meets the rounds already planned:

- Round 3 (project flow, step pages trimmed) carries Part B and the "no dead ends" rule.
- Round 4 (the step line; site pages) carries Part A's strip and Part C's sky view.
- Round 5 (Ask on the page; guide) is replaced by Part D and joined by Part E.
- Round 6 (loading and empty states; Home) carries Parts G and H.
- Round 7 (cleanup) carries Parts F and I.

Each agent gets a written brief with the files it owns, writes its report as it goes, and I check and
commit its work. One Opus and one Sonnet at a time, as before.

## 5. Rules that do not change

- No invented numbers. An assumed value has a stated reason and is hatched.
- No score, rank, verdict or "best".
- A number is never shown without its margin and its kind.
- The AI states only numbers the tools returned. The number check on the server is not touched.
- Amber is the Sun, cyan is Earth, magenta is over a limit. Two typefaces only.
- 44 px tap targets, readable contrast, keyboard access, reduced motion respected.
- `docs/report` is yours. No agent touches it.

## 6. Decisions I need from you

| # | Question | My recommendation |
|---|---|---|
| 1 | A planned mission has no site or date published. May the worked example assume one, taken from the provider's last published mission and labelled as an example? | Yes. It is the same rule already used for the rocket and pad. If you say no, 11 missions keep an empty Surface step with a "choose a site" button. |
| 2 | Answers no longer name the model. Do they still carry a small "AI" mark? | Yes. People should know a machine wrote the sentence. The model name moves to "Technical details". |
| 3 | The cancelled mission (APEX 1.0): worked example or not? | No. It shows what was published and that it was cancelled. |
| 4 | If time runs short before Friday, what must be in the video? | Part A and the sky view. They are the most visible, and both are small. |

## 7. Done means

- No mission on the list opens to an empty page. All 15 planned missions show six marks, none hollow
  except Ready.
- The legend is on screen wherever the marks are.
- A first-time visitor turns the sky view without being told.
- No model name, long dash or sentence over 20 words on any default view.
- Every answer from Ask shows its numbers as tiles and its three steps in plain words.
- The five first-time tasks each take three taps or fewer.
- All gates pass, and the final screenshots pass the Part I checklist.
