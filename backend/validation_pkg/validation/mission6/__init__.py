"""Mission6-style SpliceAI utilities for splice-playground validation.

This package re-implements the exact sequence extraction logic used in your Mission6 notebook:
  - 4000bp window with the variant at index 2000 (0-based)
  - gene-outside masking with 'N' (one-hot zeros)
  - negative strand off-by-one fix (start/end +1 before reverse-complement)
  - alt base is provided in positive-strand and reverse-complemented for '-' strand
"""

__all__ = [
    "__version__",
]

__version__ = "0.1.0"
