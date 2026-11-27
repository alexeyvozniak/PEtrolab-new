"""Stable identifiers for supported presentation-only plot markers."""
_BASE_SYMBOLS = ("circle", "square", "triangle", "diamond", "triangle_down", "pentagon", "hexagon", "star", "plus", "cross")
PLOT_SYMBOLS = frozenset(_BASE_SYMBOLS + tuple(symbol + "_open" for symbol in _BASE_SYMBOLS))

def marker_legend_signature(symbol, color):
    if symbol is None:
        return ("rect", color, None)
    if symbol not in PLOT_SYMBOLS:
        raise ValueError("plot_symbol")
    base = symbol.removesuffix("_open")
    tag = "circle" if base == "circle" else "polygon"
    return (tag, "none", color) if symbol.endswith("_open") else (tag, color, None)
