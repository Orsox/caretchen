from enum import Enum, auto


class AppState(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    REFINING = auto()
    PASTING = auto()
    ERROR = auto()
