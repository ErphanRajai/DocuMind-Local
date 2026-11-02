"""Errors that can cross process boundaries without exposing provider responses."""


class PDFProcessingError(ValueError):
    pass


class ProcessingBusyError(RuntimeError):
    pass


class GenerationError(RuntimeError):
    pass


class PDFPageNotFound(PDFProcessingError):
    pass
