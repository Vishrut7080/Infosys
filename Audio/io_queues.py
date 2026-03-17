import queue

# Queue for holding text received from the frontend's speech recognition
stt_queue = queue.Queue()

# Queue for holding text to be spoken by the frontend's text-to-speech
tts_queue = queue.Queue()
