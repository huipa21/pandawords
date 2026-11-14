"""Streaming WN-LMF records; never retain an entire Lexicon tree."""

import gzip
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET


def records(path: Path) -> Iterator[ET.Element]:
    """Yield complete lexical entries/synsets, valid only until the next iteration."""
    opener = gzip.open if path.suffix == ".gz" else open
    stack: list[ET.Element] = []
    lexicons = entries = synsets = 0
    with opener(path, "rb") as stream:
        for event, element in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                element.tag = element.tag.rsplit("}", 1)[-1]
                stack.append(element)
                if element.tag == "Lexicon":
                    if element.get("language") != "en":
                        raise ValueError("OEWN requires an English WN-LMF Lexicon")
                    lexicons += 1
                continue
            if element.tag in {"LexicalEntry", "Synset"}:
                if len(stack) < 2 or stack[-2].tag != "Lexicon":
                    raise ValueError("OEWN records must belong to a Lexicon")
                if element.tag == "LexicalEntry":
                    entries += 1
                else:
                    synsets += 1
                yield element
            stack.pop()
            # Keep record children until their enclosing record has been consumed.
            if not any(parent.tag in {"LexicalEntry", "Synset"} for parent in stack):
                if stack:
                    stack[-1].remove(element)
                element.clear()
    if not lexicons or not entries or not synsets:
        raise ValueError("OEWN requires nonempty English lexical entries and synsets")
