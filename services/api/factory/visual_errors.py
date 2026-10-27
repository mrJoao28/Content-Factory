from .security import ConfigurationRequired


class VisualRequired(ConfigurationRequired):
    state = "WAITING_FOR_ASSETS"

    def __init__(self, message, code="renderer"):
        super().__init__(message)
        self.code = "visual_" + code


class VoiceRequired(VisualRequired):
    def __init__(self, message):
        super().__init__(message, "voice")
