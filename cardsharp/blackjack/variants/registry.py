"""Registry for blackjack variants."""

from typing import Dict, Type, List
from .base import BlackjackVariant


class VariantRegistry:
    """Registry for managing blackjack variants."""
    
    _variants: Dict[str, Type[BlackjackVariant]] = {}
    
    @classmethod
    def register(cls, name: str, variant_class: Type[BlackjackVariant]) -> None:
        """Register a new variant."""
        cls._variants[name.lower()] = variant_class
    
    @classmethod
    def get(cls, name: str) -> Type[BlackjackVariant]:
        """Get a variant class by name."""
        variant = cls._variants.get(name.lower())
        if not variant:
            raise ValueError(f"Unknown variant: {name}")
        return variant
    
    @classmethod
    def list_variants(cls) -> List[str]:
        """List all registered variants."""
        return list(cls._variants.keys())