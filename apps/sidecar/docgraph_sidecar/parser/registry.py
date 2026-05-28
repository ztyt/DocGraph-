from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docgraph_sidecar.parser.base import BaseParser, ParseContext, ParseResult, normalize_extension


class ParserRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParserRegistration:
    name: str
    extensions: tuple[str, ...]
    source_types: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "extensions": list(self.extensions),
            "source_types": list(self.source_types),
        }


class ParserRegistry:
    def __init__(self, parsers: Iterable[BaseParser] | None = None) -> None:
        self._parsers_by_name: dict[str, BaseParser] = {}
        self._parsers_by_extension: dict[str, BaseParser] = {}
        self._parsers_by_source_type: dict[str, BaseParser] = {}
        for parser in parsers or ():
            self.register(parser)

    def register(self, parser: BaseParser) -> None:
        if not parser.name:
            raise ParserRegistryError("Parser name is required.")
        if parser.name in self._parsers_by_name:
            raise ParserRegistryError(f"Parser already registered: {parser.name}")

        extensions = tuple(
            extension
            for extension in (normalize_extension(item) for item in parser.supported_extensions)
            if extension
        )
        if not extensions and not parser.supported_source_types:
            raise ParserRegistryError(
                f"Parser must declare at least one extension or source type: {parser.name}"
            )

        for extension in extensions:
            existing = self._parsers_by_extension.get(extension)
            if existing is not None:
                raise ParserRegistryError(
                    f"Extension {extension} already handled by parser {existing.name}."
                )

        for source_type in parser.supported_source_types:
            existing = self._parsers_by_source_type.get(source_type)
            if existing is not None:
                raise ParserRegistryError(
                    f"Source type {source_type} already handled by parser {existing.name}."
                )

        self._parsers_by_name[parser.name] = parser
        for extension in extensions:
            self._parsers_by_extension[extension] = parser
        for source_type in parser.supported_source_types:
            self._parsers_by_source_type[source_type] = parser

    def list(self) -> tuple[ParserRegistration, ...]:
        return tuple(
            ParserRegistration(
                name=parser.name,
                extensions=parser.normalized_extensions,
                source_types=parser.supported_source_types,
            )
            for parser in sorted(self._parsers_by_name.values(), key=lambda item: item.name)
        )

    def get_by_name(self, name: str) -> BaseParser | None:
        return self._parsers_by_name.get(name)

    def get_for_extension(self, extension: str) -> BaseParser | None:
        return self._parsers_by_extension.get(normalize_extension(extension))

    def select(self, context: ParseContext) -> BaseParser | None:
        parser = self.get_for_extension(context.extension)
        if parser is not None:
            return parser
        if context.source_type:
            return self._parsers_by_source_type.get(context.source_type)
        return None

    def require(self, context: ParseContext) -> BaseParser:
        parser = self.select(context)
        if parser is None:
            raise ParserRegistryError(f"No parser registered for {context.extension or context.path}.")
        return parser

    def parse(self, context: ParseContext) -> ParseResult:
        parser = self.require(context)
        return parser.parse(context)

    def parse_path(
        self,
        path: str | Path,
        *,
        file_id: str,
        source_type: str | None = None,
    ) -> ParseResult:
        return self.parse(ParseContext.from_path(path, file_id=file_id, source_type=source_type))
