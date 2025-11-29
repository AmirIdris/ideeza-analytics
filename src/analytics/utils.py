from typing import Dict, List, Any, Optional
from django.db.models import Q
from rest_framework.exceptions import ValidationError

class InvalidFilterError(ValidationError):
    """Custom exception for clear API error messages."""
    pass

class DynamicFilterBuilder:
    """
    A recursive engine to transform JSON filter payloads into Django Q objects.
    
    Supported JSON Structure:
    {
        "operator": "and" | "or" | "not",
        "conditions": [
            { "field": "country", "op": "eq", "value": "US" },  <-- Leaf Node
            { "operator": "or", "conditions": [...] }           <-- Nested Group
        ]
    }
    """

    # Map API operators to Django Field Lookups
    # This acts as a whitelist of allowed operations.
    OPERATOR_MAPPING = {
        'eq': 'exact',
        'neq': 'exact', # Special handling for negation
        'gt': 'gt',
        'gte': 'gte',
        'lt': 'lt',
        'lte': 'lte',
        'contains': 'icontains', # Case-insensitive by default for better UX
        'startswith': 'istartswith',
    }

    def __init__(self, allowed_fields: Optional[List[str]] = None):
        """
        :param allowed_fields: List of model fields allowed to be filtered. 
                               If None, all fields are allowed (Use with caution).
        """
        self.allowed_fields = allowed_fields

    def build(self, filter_payload: Dict[str, Any]) -> Q:
        """
        The public entry point.
        Returns a Q object ready to be passed to .filter()
        """
        if not filter_payload:
            return Q()

        return self._parse_group(filter_payload)

    def _parse_group(self, group: Dict[str, Any]) -> Q:
        """
        Recursively parses a group of conditions.
        """
        operator = group.get('operator', 'and').lower()
        conditions = group.get('conditions', [])

        if not isinstance(conditions, list):
            raise InvalidFilterError("Field 'conditions' must be a list.")

        # Initialize Q object based on operator logic
        # For AND/OR, we start empty.
        # For NOT, we will negate the final result.
        q_result = Q()

        for index, condition in enumerate(conditions):
            # RECURSION CASE: Condition is a nested group
            if 'conditions' in condition:
                sub_q = self._parse_group(condition)
                q_result = self._combine(q_result, sub_q, operator, index)
            
            # BASE CASE: Condition is a leaf node
            else:
                sub_q = self._parse_leaf(condition)
                q_result = self._combine(q_result, sub_q, operator, index)

        # Handle the 'not' operator for the whole group
        if operator == 'not':
            return ~q_result
        
        return q_result

    def _combine(self, current_q: Q, new_q: Q, operator: str, index: int) -> Q:
        """
        Combines the current Q object with a new one based on the operator.
        """
        if index == 0:
            return new_q
        
        if operator == 'or':
            return current_q | new_q
        elif operator == 'and' or operator == 'not':
            # 'not' inside a group acts like AND until the very end where it flips
            return current_q & new_q
        
        return current_q & new_q # Default fallback

    def _parse_leaf(self, condition: Dict[str, Any]) -> Q:
        """
        Parses a single field condition (e.g., country == 'US').
        """
        field = condition.get('field')
        op = condition.get('op', 'eq')
        value = condition.get('value')

        if not field:
            raise InvalidFilterError("Condition missing 'field'.")

        # Security Check: Prevent arbitrary field access (e.g., password)
        if self.allowed_fields and field not in self.allowed_fields:
            # We check prefixes too for related fields (e.g. blog__title)
            # This logic can be adjusted based on strictness requirements
            base_field = field.split('__')[0]
            if base_field not in self.allowed_fields:
                 raise InvalidFilterError(f"Filtering by field '{field}' is not allowed.")

        django_lookup = self.OPERATOR_MAPPING.get(op)
        if not django_lookup:
            raise InvalidFilterError(f"Operator '{op}' is not supported.")

        # Construct the lookup string (e.g., country__exact)
        lookup_key = f"{field}__{django_lookup}"
        
        q_node = Q(**{lookup_key: value})

        # Special handling for 'neq' (Not Equal)
        if op == 'neq':
            return ~q_node
        
        return q_node