### Name and Version

llama-server 0.8.0 (b11960-8642541b2), Homebrew, macOS arm64 (Apple M2).
Code path also unchanged on master as of 2026-11-04 (v0.9.0).

### Operating systems

Mac

### Which llama.cpp modules do you know to be affected?

llama-server

### Problem description & steps to reproduce

`/v1/realtime` audio output ignores the target language/voice, so speech in
non-English languages is generated with the default (English) voice
conditioning. `llama-tts` with the same model and mmproj produces correct
speech because it passes `--tts-lang` / `--tts-voice` to the generator.

Model: `LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M` +
`mmproj-LFM3-Omni-2B-Q4_0.gguf`.

1. `llama-server -hf LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M --reasoning off --port 8091`
2. Open `ws://127.0.0.1:8091/v1/realtime`, send
   `session.update` with `{"type":"realtime","output_modalities":["text","audio"],"instructions":"Responde en español, breve."}`
3. `conversation.item.create` with Spanish `input_text`, then `response.create`.

Result: the text deltas are correct Spanish ("La reunión empieza a las
nueve."), but the audio is Spanish words with a strong English accent and
poor articulation. Re-transcribing that audio with the same server's
`/v1/audio/transcriptions` gives e.g. "Apacete yiga el martes al atraso" for
"El paquete llega el martes a las tres de la tarde". A human listener
confirms: Spanish words, English voice/accent.

Control: `llama-tts -m <model> -mm <mmproj> --tts-lang es -p "La reunión
empieza mañana a las nueve." -o out.wav` → clear Spanish; re-transcription
is exact.

With `output_modalities: ["audio"]` (audio only) the output is unintelligible
in any language (including English), and in one case it ran on for 215 s.

### Likely cause

`tools/tts/tts.cpp` renders the prompt with
`common_chat_get_tts_prompt(tmpls, prompt, tts_lang, tts_voice)` and sets
`inp.lang` / `inp.voice`. In `tools/server/server-realtime.cpp`
(`server_realtime_slot`, where `mtmd_helper::gen_audio::inp` is built, ~L1000
at b11960) only prompt, seq_id, n_past, seed, stream, out_type and out_mode
are set; there is no `lang`/`voice`, and the session schema has no field to
provide them (`language` exists only for input transcription).

### Suggestion

Accept an output language/voice in the realtime session (e.g.
`session.audio.output.voice` per the OpenAI Realtime schema, plus a language
field or server flag such as `--tts-lang`/`--tts-voice` for llama-server) and
forward them to the gen-audio input. Optionally document that
`output_modalities: ["audio"]` alone degrades models trained for interleaved
text+audio.

### First Bad Commit

Present since realtime was added in 8ca4060b7 (#31269).
