"""Data files shipped with the package (character table, and future fixtures).

Kept as a real package (not a namespace directory) so that
``importlib.resources.files("aninest.data")`` works on every supported Python,
including 3.10 where namespace-package resources are not supported.
"""
