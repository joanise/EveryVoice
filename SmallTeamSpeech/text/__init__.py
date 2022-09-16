import re
from collections import Counter
from itertools import chain
from typing import Dict

from loguru import logger
from nltk.tokenize import RegexpTokenizer

from config import ConfigError
from config.base_config import BaseConfig
from text.features import get_features


class TextProcessor:
    def __init__(self, config: BaseConfig):
        self.config = config
        self._all_symbols = self.config["text"]["symbols"]

        # apply longest characters first to apply multigraph symbols first
        self.symbols = sorted(
            list(chain.from_iterable(list(v) for v in self._all_symbols.values())),
            key=len,
            reverse=True,
        )

        self.missing_symbols: Counter[str] = Counter()
        self.duplicate_symbols: Counter[str] = Counter()

        # Mappings from symbol to numeric ID and vice versa
        self._symbol_to_id: Dict[str, int] = {}
        self._id_to_symbol: Dict[int, str] = {}
        for i, s in enumerate(self.symbols):
            if s in self._symbol_to_id:
                logger.warning(
                    f"Symbol '{s}' has already been declared at position {self._symbol_to_id[s]} so we will use that index instead of the current index {i}. Please remove duplicates from your configuration."
                )
                self.duplicate_symbols[s] += 1
            else:
                self._symbol_to_id[s] = i
                self._id_to_symbol[i] = s

        self._tokenizer = RegexpTokenizer(
            "|".join([re.escape(x) for x in self.symbols])
        )
        self._missing_symbol_finder = RegexpTokenizer(
            "|".join([re.escape(x) for x in self.symbols]),
            gaps=True,
            discard_empty=True,
        )

    def text_to_sequence(self, text):
        """Converts a string of text to a sequence of IDs corresponding to the symbols in the text.
        Args:
        text: string to convert to a sequence
        cleaner_fns: a list of fns to clean text
        Returns:
        List of integers corresponding to the symbols in the text
        """
        sequence = []
        clean_tokens = self.text_to_tokens(text)
        for symbol in clean_tokens:
            symbol_id = self._symbol_to_id[symbol]
            sequence += [symbol_id]
        return sequence

    def text_to_phonological_features(self, text):
        """Converts a string of text to a sequence of IDs corresponding to the symbols in the text.
        Args:
        text: string to convert to a sequence
        cleaner_fns: a list of fns to clean text
        Returns:
        List of phonological feature vectors
        """
        clean_text = self.text_to_tokens(text)
        return get_features(clean_text)

    def clean_text(self, text):
        """Converts some text to cleaned text"""
        for cleaner_fn in self.config["text"]["cleaners"]:
            try:
                text = cleaner_fn(text)
            except Exception as e:
                raise ConfigError(
                    f"Cleaner did not work and threw exception {e}"
                ) from e
        return text

    def text_to_tokens(self, text):
        """Converts a string of text to a sequence of tokens.
        Args:
        text: string to convert to a sequence
        cleaner_fns: a list of fns to clean text
        Returns:
        List of symbols in the text
        """
        clean_text = self.clean_text(text)
        clean_tokens = self._tokenizer.tokenize(clean_text)
        for symbol in self._missing_symbol_finder.tokenize(clean_text):
            logger.warning(
                f"Symbol '{symbol}' occurs in the text '{clean_text}' but was not declared in your configuration so it is being ignored."
            )
            self.missing_symbols[symbol] += 1
        return clean_tokens

    def cleaned_text_to_sequence(self, cleaned_text):
        """Converts a string of text to a sequence of IDs corresponding to the symbols in the text.
        Args:
        text: string to convert to a sequence
        Returns:
        List of integers corresponding to the symbols in the text
        """
        cleaned_text = self._tokenizer.tokenize(cleaned_text)
        return [self._symbol_to_id[symbol] for symbol in cleaned_text]

    def sequence_to_text(self, sequence):
        """Converts a sequence of IDs back to a string"""
        return "".join(self._id_to_symbol[symbol_id] for symbol_id in sequence)
