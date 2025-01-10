
# SST Service
```
uvicorn main:app --reload
```
That will run backend server which user can interact, as fallow:
user send audio data and server transcribe that into polish language text.


# TTS Service
1. Put into ```data/text.txt``` text you want to transcribe
2. In main directory run ```python3 edge_tts_test.py --pl``` if text is in english change ```pl``` into ```en```
3. Output file will be in ```data``` dir, named ```pl_output.mp3``` or ```en_output.mp3```

