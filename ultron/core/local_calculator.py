"""Bounded Decimal arithmetic and allowlisted unit conversion; never eval/exec."""
from __future__ import annotations

import ast
import re
from decimal import Decimal, DecimalException, localcontext


def number(value):
    if not isinstance(value, str) or len(value) > 100 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,3})?", value):
        raise ValueError("Use a decimal string with a dot separator, no commas or units.")
    result = Decimal(value)
    if not result.is_finite() or abs(result) > Decimal("1e100") or (result != 0 and abs(result) < Decimal("1e-100")):
        raise ValueError("Number outside supported finite range (absolute maximum 1e100).")
    return result


def display(value):
    return "0" if value == 0 else str(value.normalize())


def calculate(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 500:
        raise ValueError("Expression must be 1–500 characters.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, RecursionError):
        raise ValueError("Invalid arithmetic expression.") from None
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("Expression too complex.")
    expression = expression.strip()

    def visit(node, depth=0):
        if depth > 12:
            raise ValueError("Expression nesting too deep.")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return number(ast.get_source_segment(expression, node))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth + 1)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            elif isinstance(node.op, ast.Mod):
                result = left % right
            elif isinstance(node.op, ast.Pow) and right == right.to_integral_value() and abs(right) <= 12:
                result = left ** int(right)
            else:
                raise ValueError("Supported: + - * / % and integer powers between -12 and 12. % means remainder, not percent.")
            if not result.is_finite() or abs(result) > Decimal("1e100") or (result != 0 and abs(result) < Decimal("1e-100")):
                raise ValueError("Result outside supported finite range.")
            return result
        raise ValueError("Only numeric literals and arithmetic operators are supported; no functions, names or code.")

    try:
        with localcontext() as ctx:
            ctx.prec = 28
            return display(visit(tree.body))
    except DecimalException:
        raise ValueError("Undefined arithmetic or division by zero.") from None


# Dimension, scale to base unit. Values are exact decimal definitions.
UNITS = {
    "m": ("length", "1"), "cm": ("length", ".01"), "mm": ("length", ".001"),
    "km": ("length", "1000"), "in": ("length", ".0254"), "ft": ("length", ".3048"),
    "mi": ("length", "1609.344"), "kg": ("mass", "1"), "g": ("mass", ".001"),
    "lb": ("mass", ".45359237"), "oz": ("mass", ".028349523125"),
    "s": ("duration", "1"), "min": ("duration", "60"), "h": ("duration", "3600"),
    "day": ("duration", "86400"), "L": ("volume", "1"), "mL": ("volume", ".001"),
}


def convert(value, source, destination):
    value = number(value)
    if not isinstance(source, str) or not isinstance(destination, str):
        raise ValueError("Units must be strings.")
    with localcontext() as ctx:
        ctx.prec = 28
        if source in {"C", "F", "K"} and destination in {"C", "F", "K"}:
            kelvin = value if source == "K" else value + Decimal("273.15") if source == "C" else (value - 32) * 5 / 9 + Decimal("273.15")
            if kelvin < 0:
                raise ValueError("Temperature below absolute zero.")
            result = kelvin if destination == "K" else kelvin - Decimal("273.15") if destination == "C" else (kelvin - Decimal("273.15")) * 9 / 5 + 32
        else:
            if source not in UNITS or destination not in UNITS or UNITS[source][0] != UNITS[destination][0]:
                raise ValueError("Unsupported or incompatible units. Use exact supported symbols; currencies are not supported.")
            result = value * Decimal(UNITS[source][1]) / Decimal(UNITS[destination][1])
        if abs(result) > Decimal("1e100") or (result != 0 and abs(result) < Decimal("1e-100")):
            raise ValueError("Result outside supported range.")
        return display(result)
