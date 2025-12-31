"""
horizontal_scroll component - Wrapper for Swiper Element Web Components.

Usage Mode 1 - With items list (automatic slides):
    {% component "horizontal_scroll" items=categories item_template="partials/category_chip.html" %}
    {% endcomponent %}

Usage Mode 2 - With slot (custom content):
    {% component "horizontal_scroll" responsive=True %}
        {% fill "slides" %}
            <swiper-slide>Item 1</swiper-slide>
            <swiper-slide>Item 2</swiper-slide>
        {% endfill %}
    {% endcomponent %}

Features:
- Uses native Swiper Element (swiper-container, swiper-slide)
- Two modes: items list with template OR custom slot content
- Navigation arrows (built-in Swiper navigation)
- Pagination dots (optional)
- Configurable slides per view
- Responsive breakpoints for different screen sizes
- Free mode scrolling (optional)
"""

from django_components import Component, register


@register("horizontal_scroll")
class HorizontalScroll(Component):
    template_name = "horizontal_scroll/horizontal_scroll.html"

    def get_context_data(
        self,
        css_class: str = "",
        space_between: int = 12,
        slides_per_view: int = None,
        responsive: bool = False,
        navigation: bool = True,
        pagination: bool = False,
        free_mode: bool = False,
        bp_sm: int = 2,
        bp_md: int = 3,
        bp_lg: int = 3,
        bp_xl: int = 4,
        items: list = None,
        item_template: str = None,
        **kwargs
    ):
        """
        Args:
            css_class: Additional CSS classes for swiper-container
            space_between: Space between slides in pixels (default: 12)
            slides_per_view: Number of slides visible (None for 'auto')
            responsive: Enable responsive breakpoints
            navigation: Show prev/next arrows (default: True)
            pagination: Show pagination dots (default: False)
            free_mode: Enable free scrolling without snapping
            bp_sm: Slides at 320px+ (default: 2)
            bp_md: Slides at 480px+ (default: 3)
            bp_lg: Slides at 768px+ (default: 3)
            bp_xl: Slides at 1024px+ (default: 4)
            items: List of items to render as slides
            item_template: Template path for rendering each item
        """
        return {
            "css_class": css_class,
            "space_between": space_between,
            "slides_per_view": slides_per_view,
            "responsive": responsive,
            "navigation": navigation,
            "pagination": pagination,
            "free_mode": free_mode,
            "bp_sm": bp_sm,
            "bp_md": bp_md,
            "bp_lg": bp_lg,
            "bp_xl": bp_xl,
            "items": items,
            "item_template": item_template,
            **kwargs,
        }
