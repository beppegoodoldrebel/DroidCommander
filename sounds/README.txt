Droid sounds are managed in the editor's VOICE tab.

A voice is either synthesized (sliders) or made of your own sound files. For a sound-file
voice, add one or more files (WAV, OGG, FLAC, MP3) for each response:

  Acknowledged    command executed
  Error           command could not run (game not in the foreground, key not bound...)
  Not understood  phrase not understood
  Ready           app ready at startup
  Chatter         chatter (also played when commands are reloaded)

The droid plays one of a response's files at random. A response with no files uses the
synthesized voice.

When you save a voice, its files are copied into  sounds\voices\<voice name>\<response>\
so the voice keeps working even if you move or delete the originals.
