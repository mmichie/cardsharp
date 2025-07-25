"""Blackjack variant system."""

from .base import BlackjackVariant
from .registry import VariantRegistry
from .classic import ClassicBlackjackVariant
from .spanish21 import Spanish21Variant

# Register built-in variants
VariantRegistry.register("classic", ClassicBlackjackVariant)
VariantRegistry.register("spanish21", Spanish21Variant)

__all__ = ["BlackjackVariant", "VariantRegistry", "ClassicBlackjackVariant", "Spanish21Variant"]