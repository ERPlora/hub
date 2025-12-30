from django_components import Component, register


@register("setting_textarea")
class SettingTextarea(Component):
    """
    Setting textarea component for settings pages.
    Displays a title, description and a multi-line text area.
    """

    template_name = "setting_textarea/setting_textarea.html"

    def get_context_data(
        self,
        name="",
        title="",
        description="",
        value="",
        placeholder="",
        rows=3,
        disabled=False,
        **kwargs
    ):
        return {
            "name": name,
            "title": title,
            "description": description,
            "value": value,
            "placeholder": placeholder,
            "rows": rows,
            "disabled": disabled,
        }
