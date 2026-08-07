"""CNKI2WOS public package interface."""

from .core import ConversionError, ConversionResult, convert_file, convert_text

__all__ = ["ConversionError", "ConversionResult", "convert_file", "convert_text"]
__version__ = "1.0.0"
