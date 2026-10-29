"""Source adapters. Each exposes fetch_region(region_id, bbox) -> list[record].

Adding a source is one new module here plus a line in build.SOURCES. The
adapter does the fetching and maps raw tags onto opencam.normalize records; it
never dedupes or writes packs.
"""
