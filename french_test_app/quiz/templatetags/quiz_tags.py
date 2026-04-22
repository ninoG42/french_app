from django import template

register = template.Library()


@register.filter
def percentage(value):
    if value is None:
        return "0%"
    try:
        return f"{float(value) * 100:.0f}%"
    except (ValueError, TypeError):
        return "0%"
