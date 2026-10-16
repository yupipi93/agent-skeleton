"""Executive cloud-cost report generator.

parse    read Google Cloud Billing CSV exports
metrics  turn an export plus config into one canonical set of figures
charts   inline SVG chart builders, print-safe
render   assemble the paginated, self-contained HTML document
"""

__all__ = ["parse", "metrics", "charts", "render"]
