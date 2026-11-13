# Vision

## Goal

A web app (installable as a PWA) for learning English vocabulary in depth. Each word is a node in
a personal knowledge graph rather than an isolated flashcard. Learning and review are scheduled
using memory research.

Current language pair: **target English, source Chinese**. Both are stored as fields (`target_lang`,
`source_lang`) so other pairs can be added later without schema changes.

## Users

- **Admin**: bootstrapped from the environment and creates all other accounts. There is no self-signup.
- **User**: fully independent. There are no friends, sharing links or shared notebooks. Users share
  content only by exporting and importing files.

## Core ideas

| Idea | How it appears in the app |
|---|---|
| Word structure | Lemma → lexeme (part of speech/etymology) → sense, with US/UK pronunciation per lexeme |
| Projects | Notebooks (e.g. "IELTS") holding a trimmed tree of selected lemmas and senses |
| All words | The union of a user's projects, shown as one graph |
| Personal edits | A user can override any field of shared dictionary data. Hiding is per project |
| Phrases | Multi-word lemmas (idioms, phrasal verbs) with their own senses, linked to their component words |
| Context | Sentences and passages linked to the senses they use |

## Learning theories → features

| Theory | Feature |
|---|---|
| Ebbinghaus forgetting curve / spaced repetition | FSRS scheduling per sense, daily plan, exam-date pacing |
| Contextual learning | Sentences, passages, context tags, cloze exercises, reading view |
| Retrieval practice | def→word, word→def, cloze, listen→spell, scenario→word, relation quiz |
| Dual coding & mnemonics | Audio (US/UK), images (upload/Pixabay), mnemonic notes |
| Depth of processing | Graph relations (synonym, antonym, derivation, morphemes, tags), graph exploration, relation quizzes |

## Non-goals (for now)

- Social features, shared editing, leaderboards
- Languages other than English as the target
- Native mobile apps (we ship a PWA instead)
- Hosted CI/CD
