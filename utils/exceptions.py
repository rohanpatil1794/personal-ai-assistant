class AssistantError(Exception):
    """Base exception for all assistant errors."""


class ConfigError(AssistantError):
    """Raised when required configuration is missing or invalid."""


class STTError(AssistantError):
    """Raised when speech-to-text fails."""


class TTSError(AssistantError):
    """Raised when text-to-speech fails."""


class HAClientError(AssistantError):
    """Raised when a Home Assistant API call fails."""


class GeminiError(AssistantError):
    """Raised when Gemini API call fails."""


class AudioError(AssistantError):
    """Raised when mic capture or playback fails."""
