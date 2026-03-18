import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB_PATH = os.path.join(BASE_DIR, 'users.db')
ADMIN_DB_PATH = os.path.join(BASE_DIR, 'admins.db')

AUDIO_WORD_BANK = [
    "cobalt", "falcon", "granite", "maple", "cedar", "amber", "canyon",
    "ember", "glacial", "haven", "inlet", "juniper", "kindle", "lumen",
    "mossy", "nimbus", "obsidian", "pebble", "quartz", "russet",
    "nebula", "pulsar", "zenith", "solstice", "corona", "vortex",
    "photon", "kelvin", "titan", "cosmos", "lunar", "stellar",
    "bastion", "cipher", "delta", "echo", "foxtrot", "vector",
    "kestrel", "phantom", "ridgeback", "summit", "tundra", "ultra",
    "blue falcon", "red cedar", "dark ember", "cold zenith",
    "swift maple", "iron cliff", "pale comet", "loud thunder",
]


def suggest_audio_word() -> str:
    """Return a random pronounceable secret audio word from the bank."""
    return random.choice(AUDIO_WORD_BANK)
