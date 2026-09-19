"""Tolerant s-expression reader for .kicad_pcb files.

Every node remembers its span in the source text. A document is edited by splicing text
(``apply_edits``), so regions we do not touch are emitted byte-for-byte. That is what lets us
rewrite files whose full schema we do not know.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

LIST, ATOM, STRING = "list", "atom", "string"
_WS = " \t\r\n"


class ParseError(ValueError):
    """Raised when the text is not a single balanced s-expression."""


@dataclass
class Node:
    kind: str
    start: int
    end: int
    value: str = ""  # atom text, or unescaped string contents
    children: list["Node"] = field(default_factory=list)

    @property
    def head(self) -> Optional[str]:
        """Name of a list node, e.g. 'zone' for (zone ...); None otherwise."""
        if self.kind == LIST and self.children and self.children[0].kind == ATOM:
            return self.children[0].value
        return None

    @property
    def args(self) -> list["Node"]:
        """Children after the head."""
        return self.children[1:] if self.kind == LIST else []

    def find(self, name: str) -> Optional["Node"]:
        """First direct child list whose head is ``name``."""
        for child in self.children:
            if child.kind == LIST and child.head == name:
                return child
        return None

    def find_all(self, name: str) -> list["Node"]:
        return [c for c in self.children if c.kind == LIST and c.head == name]

    def text_arg(self, index: int = 0) -> Optional[str]:
        """Value of the ``index``-th argument if it is an atom or string."""
        args = self.args
        if index < len(args) and args[index].kind in (ATOM, STRING):
            return args[index].value
        return None


def _attach(stack: list[Node], node: Node, where: int) -> None:
    if not stack:
        raise ParseError(f"token outside the root expression at offset {where}")
    stack[-1].children.append(node)


def parse(text: str) -> Node:
    """Parse ``text`` into its single root list node."""
    stack: list[Node] = []
    root: Optional[Node] = None
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in _WS:
            i += 1
        elif c == "(":
            node = Node(LIST, i, -1)
            if stack:
                stack[-1].children.append(node)
            elif root is not None:
                raise ParseError(f"second root expression at offset {i}")
            stack.append(node)
            i += 1
        elif c == ")":
            if not stack:
                raise ParseError(f"unbalanced ')' at offset {i}")
            node = stack.pop()
            node.end = i + 1
            if not stack:
                root = node
            i += 1
        elif c == '"':
            j, chars = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    esc = text[j + 1]
                    chars.append({"n": "\n", "t": "\t"}.get(esc, esc))
                    j += 2
                else:
                    chars.append(text[j])
                    j += 1
            if j >= n:
                raise ParseError(f"unterminated string starting at offset {i}")
            _attach(stack, Node(STRING, i, j + 1, "".join(chars)), i)
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in _WS and text[j] not in '()"':
                j += 1
            _attach(stack, Node(ATOM, i, j, text[i:j]), i)
            i = j
    if stack:
        raise ParseError("unbalanced '(' at end of input")
    if root is None:
        raise ParseError("empty document")
    return root


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: str = ""


def delete_node(text: str, node: Node) -> Edit:
    """Edit that removes ``node`` together with the whitespace in front of it."""
    start = node.start
    while start > 0 and text[start - 1] in _WS:
        start -= 1
    return Edit(start, node.end)


def apply_edits(text: str, edits: Iterable[Edit]) -> str:
    """Apply non-overlapping edits to ``text``. With no edits the text is returned unchanged."""
    out: list[str] = []
    pos = 0
    for edit in sorted(edits, key=lambda e: (e.start, e.end)):
        if edit.start < pos:
            raise ValueError(f"overlapping edits at offset {edit.start}")
        out.append(text[pos:edit.start])
        out.append(edit.replacement)
        pos = edit.end
    out.append(text[pos:])
    return "".join(out)
